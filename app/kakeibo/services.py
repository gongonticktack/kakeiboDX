"""明細の保存、集計、節約助言を行う。"""

import hashlib
import re
import unicodedata
import uuid
from collections import Counter
from datetime import date, datetime
from difflib import SequenceMatcher
from pathlib import Path

import psycopg

from .db import get_db
from .parser import ParsedTransaction, categorize, parse_pdf


SINGLE_PERSON_MONTHLY_AVERAGES = {
    "食費": 43941,
    "日用品": 12816,
    "娯楽": 19519,
    "固定費": 36188,
    "交通": 20418,
    "医療・健康": 8394,
    "自己投資": 900,
    "資産形成": 0,
    "衣服・美容": 4881,
}
AVERAGE_SOURCE_LABEL = "総務省統計局 家計調査 2024年 単身世帯の月平均"
AVERAGE_EXCLUDED_CATEGORIES = {"自己投資", "資産形成"}


def floor_to_hundreds(value: int) -> int:
    """100円未満を切り捨てる。

    Args:
        value: 丸める金額。

    Returns:
        100円単位に切り捨てた金額。
    """
    return value // 100 * 100


def merchant_key(merchant: str) -> str:
    """似た店舗名をまとめるためのキーを作る。

    Args:
        merchant: 店舗名。

    Returns:
        比較用に正規化した店舗名。
    """
    normalized = unicodedata.normalize("NFKC", merchant).upper()
    normalized = re.sub(r"利用国[A-Z]{2}", "", normalized)
    return re.sub(r"\W+", "", normalized)


def similar_merchant_key(left: str, right: str) -> bool:
    """店舗名キーが似ているか判定する。

    Args:
        left: 比較する店舗名キー。
        right: 比較する店舗名キー。

    Returns:
        似た店舗名ならTrue。
    """
    if not left or not right:
        return False
    shorter, longer = sorted((left, right), key=len)
    if len(shorter) >= 5 and shorter in longer:
        return True
    return SequenceMatcher(None, left, right).ratio() >= 0.82


def learned_category(connection: psycopg.Connection, merchant: str, fallback: str) -> str:
    """学習済みカテゴリがあれば返す。

    Args:
        connection: 確認に使うDB接続。
        merchant: 店舗名。
        fallback: ルールが無い時のカテゴリ。

    Returns:
        適用するカテゴリ。
    """
    target_key = merchant_key(merchant)
    rows = connection.execute(
        "SELECT merchant_key, category FROM category_rules"
    ).fetchall()
    for row in rows:
        if similar_merchant_key(target_key, row["merchant_key"]):
            return row["category"]
    return fallback


def learn_category(connection: psycopg.Connection, merchant: str, category: str) -> int:
    """店舗名に対するカテゴリ修正を学習して既存明細へ反映する。

    Args:
        connection: 更新に使うDB接続。
        merchant: 修正された店舗名。
        category: 修正後カテゴリ。

    Returns:
        更新した既存明細件数。
    """
    target_key = merchant_key(merchant)
    connection.execute(
        """
        INSERT INTO category_rules(merchant_key, category, sample_merchant, updated_at)
        VALUES (%s, %s, %s, NOW())
        ON CONFLICT (merchant_key) DO UPDATE
        SET category = EXCLUDED.category,
            sample_merchant = EXCLUDED.sample_merchant,
            updated_at = NOW()
        """,
        (target_key, category, merchant),
    )
    rows = connection.execute("SELECT id, merchant FROM transactions").fetchall()
    target_ids = [
        row["id"]
        for row in rows
        if similar_merchant_key(target_key, merchant_key(row["merchant"]))
    ]
    if not target_ids:
        return 0
    cursor = connection.execute(
        "UPDATE transactions SET category = %s WHERE id = ANY(%s)",
        (category, target_ids),
    )
    return cursor.rowcount


def transaction_source_hash(file_hash: str, row_index: int, item: ParsedTransaction) -> str:
    """PDF内の明細行ごとに一意なハッシュを作る。

    Args:
        file_hash: PDFファイル全体のハッシュ。
        row_index: PDF内で読み取った明細の順番。
        item: 読み取った明細。

    Returns:
        DB重複判定に使うハッシュ。
    """
    identity = (
        f"{file_hash}|{row_index}|{item.used_at.isoformat()}|"
        f"{item.merchant}|{item.amount}|{item.payment_method}"
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def save_transactions(
    connection: psycopg.Connection,
    import_id: int,
    file_hash: str,
    transactions: list[ParsedTransaction],
) -> int:
    """明細一覧をDBへ保存する。

    Args:
        connection: 保存に使うDB接続。
        import_id: statement_importsのID。
        file_hash: PDFファイル全体のハッシュ。
        transactions: 保存する明細一覧。

    Returns:
        新規保存件数。
    """
    saved = 0
    for row_index, item in enumerate(transactions, start=1):
        cursor = connection.execute(
            """
            INSERT INTO transactions
                (import_id, used_at, time_known, merchant, amount, category, payment_method, source_hash)
            VALUES (%s, %s, FALSE, %s, %s, %s, %s, %s)
            ON CONFLICT (source_hash) DO NOTHING
            """,
            (
                import_id,
                item.used_at,
                item.merchant,
                item.amount,
                learned_category(connection, item.merchant, item.category),
                item.payment_method,
                transaction_source_hash(file_hash, row_index, item),
            ),
        )
        saved += cursor.rowcount
    return saved


def transaction_match_key(item: ParsedTransaction) -> tuple:
    """既存明細との照合キーを作る。

    Args:
        item: 読み取った明細。

    Returns:
        同じ利用を数えるためのキー。
    """
    return (item.used_at, item.merchant, item.amount, item.payment_method)


def transaction_match_counts(transactions: list[ParsedTransaction]) -> Counter:
    """明細一覧を内容ごとの件数にまとめる。

    Args:
        transactions: PDFから読み取った明細一覧。

    Returns:
        明細内容をキーにした件数。
    """
    return Counter(transaction_match_key(item) for item in transactions)


def has_same_statement_content(
    connection: psycopg.Connection,
    transactions: list[ParsedTransaction],
) -> bool:
    """同じ明細内容の取込が既にあるか確認する。

    Args:
        connection: 確認に使うDB接続。
        transactions: PDFから読み取った明細一覧。

    Returns:
        同じ内容が既にあればTrue。
    """
    expected = transaction_match_counts(transactions)
    candidates = connection.execute(
        """
        SELECT id
        FROM statement_imports
        WHERE transaction_count = %s
        """,
        (len(transactions),),
    ).fetchall()
    for candidate in candidates:
        rows = connection.execute(
            """
            SELECT used_at, merchant, amount, payment_method
            FROM transactions
            WHERE import_id = %s
            """,
            (candidate["id"],),
        ).fetchall()
        if len(rows) != len(transactions):
            continue
        existing = Counter(
            (row["used_at"], row["merchant"], row["amount"], row["payment_method"])
            for row in rows
        )
        if existing == expected:
            return True
    return False


def remember_category_for_transaction(transaction_id: int, category: str) -> int:
    """手動変更したカテゴリを似た店舗名へ学習・反映する。

    Args:
        transaction_id: 基準にする明細ID。
        category: 変更後のカテゴリ。

    Returns:
        更新した明細件数。
    """
    with get_db() as connection:
        base = connection.execute(
            "SELECT merchant FROM transactions WHERE id = %s",
            (transaction_id,),
        ).fetchone()
        if not base:
            return 0
        key = merchant_key(base["merchant"])
        connection.execute(
            """
            INSERT INTO category_rules(merchant_key, category, sample_merchant, updated_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (merchant_key) DO UPDATE
            SET category = EXCLUDED.category,
                sample_merchant = EXCLUDED.sample_merchant,
                updated_at = NOW()
            """,
            (key, category, base["merchant"]),
        )
        rows = connection.execute("SELECT id, merchant FROM transactions").fetchall()
        target_ids = [
            row["id"]
            for row in rows
            if similar_merchant_key(key, merchant_key(row["merchant"]))
        ]
        if not target_ids:
            return 0
        cursor = connection.execute(
            "UPDATE transactions SET category = %s WHERE id = ANY(%s)",
            (category, target_ids),
        )
        return cursor.rowcount


def save_missing_transactions(
    connection: psycopg.Connection,
    import_id: int,
    file_hash: str,
    transactions: list[ParsedTransaction],
) -> int:
    """既存取込から足りない明細だけを追加する。

    Args:
        connection: 保存に使うDB接続。
        import_id: statement_importsのID。
        file_hash: PDFファイル全体のハッシュ。
        transactions: PDFから読み取った明細一覧。

    Returns:
        追加保存件数。
    """
    existing_rows = connection.execute(
        """
        SELECT used_at, merchant, amount, payment_method
        FROM transactions
        WHERE import_id = %s
        """,
        (import_id,),
    ).fetchall()
    remaining_existing = {}
    for row in existing_rows:
        key = (row["used_at"], row["merchant"], row["amount"], row["payment_method"])
        remaining_existing[key] = remaining_existing.get(key, 0) + 1

    missing = []
    for row_index, item in enumerate(transactions, start=1):
        key = transaction_match_key(item)
        if remaining_existing.get(key, 0):
            remaining_existing[key] -= 1
        else:
            missing.append((row_index, item))

    saved = 0
    for row_index, item in missing:
        cursor = connection.execute(
            """
            INSERT INTO transactions
                (import_id, used_at, time_known, merchant, amount, category, payment_method, source_hash)
            VALUES (%s, %s, FALSE, %s, %s, %s, %s, %s)
            ON CONFLICT (source_hash) DO NOTHING
            """,
            (
                import_id,
                item.used_at,
                item.merchant,
                item.amount,
                learned_category(connection, item.merchant, item.category),
                item.payment_method,
                transaction_source_hash(file_hash, row_index, item),
            ),
        )
        saved += cursor.rowcount
    return saved


def import_statement(path: Path, original_name: str) -> tuple[int, int]:
    """PDFを解析し、重複を除いてDBへ保存する。

    Args:
        path: 保存済みPDFのパス。
        original_name: アップロード時のファイル名。

    Returns:
        抽出件数と新規保存件数。
    """
    file_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    transactions, statement_date = parse_pdf(path)
    if not transactions:
        raise ValueError("利用明細を読み取れませんでした。楽天カードの請求明細PDFか確認してください。")
    with get_db() as connection:
        existing = connection.execute(
            "SELECT id FROM statement_imports WHERE file_hash = %s", (file_hash,)
        ).fetchone()
        if existing:
            linked_count = connection.execute(
                "SELECT COUNT(*) AS count FROM transactions WHERE import_id = %s",
                (existing["id"],),
            ).fetchone()["count"]
            if linked_count >= len(transactions):
                return len(transactions), 0
            saved = save_missing_transactions(
                connection,
                existing["id"],
                file_hash,
                transactions,
            )
            return len(transactions), saved
        if has_same_statement_content(connection, transactions):
            return len(transactions), 0
        else:
            imported = connection.execute(
                """
                INSERT INTO statement_imports(file_name, file_hash, statement_date, transaction_count)
                VALUES (%s, %s, %s, %s) RETURNING id
                """,
                (original_name, file_hash, statement_date, len(transactions)),
            ).fetchone()
            import_id = imported["id"]
        saved = save_transactions(connection, import_id, file_hash, transactions)
    return len(transactions), saved


def add_manual_transaction(
    used_at: datetime,
    merchant: str,
    amount: int,
    category: str,
    payment_method: str,
) -> int:
    """画面から入力された明細を保存する。

    Args:
        used_at: 利用日時。
        merchant: 店舗名や内容。
        amount: 金額。
        category: カテゴリ。
        payment_method: 支払方法。

    Returns:
        保存した明細ID。
    """
    source_hash = hashlib.sha256(f"manual|{uuid.uuid4().hex}".encode("utf-8")).hexdigest()
    with get_db() as connection:
        row = connection.execute(
            """
            INSERT INTO transactions
                (import_id, used_at, time_known, merchant, amount, category, payment_method, source_hash)
            VALUES (NULL, %s, FALSE, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (used_at, merchant, amount, category, payment_method, source_hash),
        ).fetchone()
        return int(row["id"])


SORT_COLUMNS = {
    "date": "used_at",
    "merchant": "merchant",
    "category": "category",
    "amount": "amount",
}


def refresh_other_categories() -> int:
    """その他の明細を現在の分類ルールで再判定する。

    Args:
        なし。

    Returns:
        更新した明細件数。
    """
    with get_db() as connection:
        rows = connection.execute(
            "SELECT id, merchant FROM transactions WHERE category = %s",
            ("その他",),
        ).fetchall()
        updates = []
        for row in rows:
            category = categorize(row["merchant"])
            if category != "その他":
                updates.append((category, row["id"]))
        for category, transaction_id in updates:
            connection.execute(
                "UPDATE transactions SET category = %s WHERE id = %s",
                (category, transaction_id),
            )
        return len(updates)


def dashboard_data(
    period: str,
    selected: str | None,
    category_filter: str | None = None,
    sort_key: str = "date",
    sort_dir: str = "desc",
) -> dict:
    """指定期間のダッシュボード用集計を返す。

    Args:
        period: month、year、allのいずれか。
        selected: YYYY-MMまたはYYYY。
        category_filter: 明細だけを絞り込むカテゴリ。
        sort_key: 明細一覧のソート項目。
        sort_dir: ascまたはdesc。

    Returns:
        合計、カテゴリ、月別推移、助言を含む辞書。
    """
    refresh_other_categories()
    where, params, label = _period_filter(period, selected)
    recent_where, recent_params = _transaction_filter(period, selected, category_filter)
    order_column = SORT_COLUMNS.get(sort_key, "used_at")
    direction = "ASC" if sort_dir == "asc" else "DESC"
    secondary_direction = direction if order_column == "used_at" else "DESC"
    with get_db() as connection:
        total_row = connection.execute(
            f"SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS count FROM transactions {where}",
            params,
        ).fetchone()
        categories = connection.execute(
            f"""
            SELECT category, SUM(amount)::BIGINT AS amount, COUNT(*) AS count
            FROM transactions {where}
            GROUP BY category ORDER BY amount DESC
            """,
            params,
        ).fetchall()
        monthly = connection.execute(
            """
            SELECT TO_CHAR(DATE_TRUNC('month', used_at), 'YYYY-MM') AS month,
                   SUM(amount)::BIGINT AS amount
            FROM transactions
            GROUP BY DATE_TRUNC('month', used_at)
            ORDER BY DATE_TRUNC('month', used_at)
            """
        ).fetchall()
        recent = connection.execute(
            f"""
            SELECT id, used_at, time_known, merchant, amount, category
            FROM transactions {recent_where}
            ORDER BY {order_column} {direction}, id {secondary_direction}
            """,
            recent_params,
        ).fetchall()
    advice = build_advice(categories, total_row["total"])
    average_insights = build_average_insights(period, categories)
    average_comparison = build_average_comparison(period, categories)
    return {
        "label": label,
        "total": total_row["total"],
        "count": total_row["count"],
        "categories": [dict(row) for row in categories],
        "monthly": [dict(row) for row in monthly],
        "recent": recent,
        "advice": advice,
        "average_insights": average_insights,
        "average_comparison": average_comparison,
        "average_source": AVERAGE_SOURCE_LABEL,
        "active_category": category_filter or "",
        "navigation": period_navigation(period, selected),
        "sort_key": sort_key,
        "sort_dir": sort_dir,
    }


def shift_period_value(period: str, selected: str | None, step: int) -> str:
    """月または年の選択値を前後へ動かす。

    Args:
        period: monthまたはyear。
        selected: 現在の選択値。
        step: 移動量。前へは-1、次へは1。

    Returns:
        移動後の選択値。
    """
    if period == "year":
        year = safe_year(selected)
        return str(year + step)
    year, month = safe_year_month(selected)
    month += step
    if month < 1:
        year -= 1
        month = 12
    elif month > 12:
        year += 1
        month = 1
    return f"{year:04d}-{month:02d}"


def safe_year(value: str | None) -> int:
    """年指定を安全な整数へ変換する。

    Args:
        value: URLなどから渡された年。

    Returns:
        有効な年。読めない場合は今年。
    """
    today = date.today()
    try:
        year = int(value or today.year)
    except (TypeError, ValueError):
        return today.year
    if year < 2000 or year > 2100:
        return today.year
    return year


def safe_year_month(value: str | None) -> tuple[int, int]:
    """年月指定を安全な年月へ変換する。

    Args:
        value: URLなどから渡されたYYYY-MM形式の値。

    Returns:
        有効な年と月。読めない場合は今月。
    """
    today = date.today()
    if not value:
        return today.year, today.month
    try:
        year_text, month_text = value.split("-", 1)
        year = int(year_text)
        month = int(month_text)
    except (TypeError, ValueError):
        return today.year, today.month
    if year < 2000 or year > 2100 or month < 1 or month > 12:
        return today.year, today.month
    return year, month


def normalize_period_value(period: str, selected: str | None) -> str:
    """画面表示用の期間値を正しい形式へ整える。

    Args:
        period: month、year、allのいずれか。
        selected: URLなどから渡された期間値。

    Returns:
        画面フォームへ入れる期間値。累計では空文字。
    """
    if period == "year":
        return str(safe_year(selected))
    if period == "all":
        return ""
    year, month = safe_year_month(selected)
    return f"{year:04d}-{month:02d}"


def period_navigation(period: str, selected: str | None) -> dict | None:
    """期間移動リンク用の値を作る。

    Args:
        period: month、year、allのいずれか。
        selected: 現在の選択値。

    Returns:
        前後の値。累計ではNone。
    """
    if period not in {"month", "year"}:
        return None
    return {
        "previous": shift_period_value(period, selected, -1),
        "next": shift_period_value(period, selected, 1),
    }


def _period_filter(period: str, selected: str | None) -> tuple[str, tuple, str]:
    """画面の期間指定をSQL条件へ変換する。

    Args:
        period: 集計単位。
        selected: 選択した年月。

    Returns:
        WHERE句、引数、表示ラベル。
    """
    if period == "year":
        year = safe_year(selected)
        return (
            "WHERE used_at >= %s AND used_at < %s",
            (date(year, 1, 1), date(year + 1, 1, 1)),
            f"{year}年",
        )
    if period == "all":
        return "", (), "累計"
    year, month = safe_year_month(selected)
    next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)
    return (
        "WHERE used_at >= %s AND used_at < %s",
        (date(year, month, 1), date(next_year, next_month, 1)),
        f"{year}年{month}月",
    )


def _transaction_filter(period: str, selected: str | None, category: str | None) -> tuple[str, tuple]:
    """明細一覧用の絞り込み条件を作る。

    Args:
        period: 集計単位。
        selected: 選択した年月。
        category: 絞り込むカテゴリ。

    Returns:
        WHERE句とSQL引数。
    """
    where, params, _label = _period_filter(period, selected)
    conditions = []
    if where:
        conditions.append(where.removeprefix("WHERE "))
    values = list(params)
    if category:
        conditions.append("category = %s")
        values.append(category)
    if not conditions:
        return "", ()
    return "WHERE " + " AND ".join(conditions), tuple(values)


def build_average_insights(period: str, categories: list[dict]) -> list[str]:
    """一人暮らし平均より多いカテゴリを見つける。

    Args:
        period: month、year、allのいずれか。
        categories: カテゴリ別集計。

    Returns:
        平均超過カテゴリの短い指摘一覧。
    """
    if period not in {"month", "year"}:
        return ["平均比較は月表示または年表示で確認できます。"]
    multiplier = 12 if period == "year" else 1
    period_label = "年" if period == "year" else "月"
    insights = []
    for row in categories:
        category = row["category"]
        if category in AVERAGE_EXCLUDED_CATEGORIES:
            continue
        average = SINGLE_PERSON_MONTHLY_AVERAGES.get(category, 0) * multiplier
        amount = int(row["amount"])
        if average <= 0 or amount < average * 1.2:
            continue
        over = amount - average
        insights.append(
            {
                "category": category,
                "amount": amount,
                "average": average,
                "over": over,
                "ratio": amount / average,
            }
        )
    insights.sort(key=lambda item: item["over"], reverse=True)
    if not insights:
        return [f"{period_label}単位では、平均を大きく超えているカテゴリは見つかりません。"]
    return [
        (
            f"「{item['category']}」が平均{floor_to_hundreds(item['average']):,}円に対して"
            f"{item['amount']:,}円で、{item['over']:,}円多めです。"
        )
        for item in insights[:3]
    ]


def build_average_comparison(period: str, categories: list[dict]) -> list[dict]:
    """平均比較グラフ用のカテゴリ別データを作る。

    Args:
        period: month、year、allのいずれか。
        categories: カテゴリ別集計。

    Returns:
        カテゴリ、支出、平均、差額の一覧。累計では空。
    """
    if period not in {"month", "year"}:
        return []
    multiplier = 12 if period == "year" else 1
    amounts = {row["category"]: int(row["amount"]) for row in categories}
    rows = []
    for category, monthly_average in SINGLE_PERSON_MONTHLY_AVERAGES.items():
        if category in AVERAGE_EXCLUDED_CATEGORIES:
            continue
        average = monthly_average * multiplier
        amount = amounts.get(category, 0)
        rows.append(
            {
                "category": category,
                "amount": amount,
                "average": floor_to_hundreds(average),
                "difference": amount - average,
            }
        )
    rows.sort(key=lambda row: row["difference"], reverse=True)
    return rows


def build_advice(categories: list[dict], total: int) -> list[str]:
    """集計結果から実行しやすい節約案を作る。

    Args:
        categories: カテゴリ別集計。
        total: 期間内合計。

    Returns:
        日本語の節約アドバイス一覧。
    """
    if not total:
        return ["PDF明細を取り込むと、支出割合に応じたアドバイスを表示します。"]
    amounts = {row["category"]: int(row["amount"]) for row in categories}
    candidates: list[tuple[int, str]] = []

    def add_advice(category: str, threshold_ratio: float, message: str) -> None:
        """条件を満たすカテゴリ助言を候補へ入れる。

        Args:
            category: 確認するカテゴリ。
            threshold_ratio: 合計に対する比率のしきい値。
            message: 表示する助言。

        Returns:
            なし。
        """
        amount = amounts.get(category, 0)
        if amount and amount / total >= threshold_ratio:
            candidates.append((amount, message))

    food = amounts.get("食費", 0)
    if food / total >= 0.25:
        candidates.append((food, f"食費が全体の{food / total:.0%}です。コンビニや外食を週1回減らす目標から始めましょう。"))
    if food >= 50000:
        candidates.append((food, f"食費が{food:,}円あります。よく買う定番品だけでも週末にまとめ買いすると、細かい買い足しを減らせます。"))

    add_advice("日用品", 0.12, f"日用品が{amounts.get('日用品', 0):,}円です。通販のついで買いを防ぐため、購入前にカートを一晩置くルールが効きます。")
    add_advice("娯楽", 0.10, f"娯楽費が{amounts.get('娯楽', 0):,}円あります。未使用のゲーム・動画・音楽サブスクを先に確認すると効果的です。")
    add_advice("固定費", 0.18, f"固定費は{amounts.get('固定費', 0):,}円です。通信・電気・サブスクは半年ごとに契約内容を見直しましょう。")
    add_advice("交通", 0.12, f"交通費が{amounts.get('交通', 0):,}円です。タクシーや都度チャージが多い月は、予定を寄せて移動回数を減らせないか見直しましょう。")
    add_advice("衣服・美容", 0.08, f"衣服・美容が{amounts.get('衣服・美容', 0):,}円です。セール前に必要な物リストを決めて、似た用途の買い足しを避けましょう。")
    add_advice("医療・健康", 0.08, f"医療・健康が{amounts.get('医療・健康', 0):,}円です。薬やケア用品は重複しやすいので、家の在庫を見てから買うと無駄を抑えられます。")
    top = next(
        (row for row in categories if row["category"] not in AVERAGE_EXCLUDED_CATEGORIES),
        None,
    )
    if top:
        top_amount = int(top["amount"])
        candidates.append((top_amount, f"最大カテゴリは「{top['category']}」の{top_amount:,}円です。まず5%削減で月{int(top_amount * 0.05):,}円を目安にできます。"))
    candidates.sort(key=lambda item: item[0], reverse=True)
    if candidates:
        return [message for _amount, message in candidates[:3]]
    return ["自己投資や資産形成が中心の支出です。節約よりも、使ったお金が学びや将来の備えにつながっているかを確認しましょう。"]
