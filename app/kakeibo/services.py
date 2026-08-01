"""明細の保存、集計、節約助言を行う。"""

import hashlib
from collections import Counter
from datetime import date
from pathlib import Path

import psycopg

from .db import get_db
from .parser import ParsedTransaction, parse_pdf


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
                item.category,
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
                item.category,
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


def dashboard_data(period: str, selected: str | None) -> dict:
    """指定期間のダッシュボード用集計を返す。

    Args:
        period: month、year、allのいずれか。
        selected: YYYY-MMまたはYYYY。

    Returns:
        合計、カテゴリ、月別推移、助言を含む辞書。
    """
    where, params, label = _period_filter(period, selected)
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
            FROM transactions {where}
            ORDER BY used_at DESC, id DESC LIMIT 12
            """,
            params,
        ).fetchall()
    advice = build_advice(categories, total_row["total"])
    return {
        "label": label,
        "total": total_row["total"],
        "count": total_row["count"],
        "categories": [dict(row) for row in categories],
        "monthly": [dict(row) for row in monthly],
        "recent": recent,
        "advice": advice,
    }


def _period_filter(period: str, selected: str | None) -> tuple[str, tuple, str]:
    """画面の期間指定をSQL条件へ変換する。

    Args:
        period: 集計単位。
        selected: 選択した年月。

    Returns:
        WHERE句、引数、表示ラベル。
    """
    today = date.today()
    if period == "year":
        year = int(selected or today.year)
        return (
            "WHERE used_at >= %s AND used_at < %s",
            (date(year, 1, 1), date(year + 1, 1, 1)),
            f"{year}年",
        )
    if period == "all":
        return "", (), "累計"
    value = selected or today.strftime("%Y-%m")
    year, month = map(int, value.split("-"))
    next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)
    return (
        "WHERE used_at >= %s AND used_at < %s",
        (date(year, month, 1), date(next_year, next_month, 1)),
        f"{year}年{month}月",
    )


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
    advice: list[str] = []
    food = amounts.get("食費", 0)
    if food / total >= 0.25:
        advice.append(f"食費が全体の{food / total:.0%}です。コンビニや外食を週1回減らす目標から始めましょう。")
    entertainment = amounts.get("娯楽", 0)
    if entertainment / total >= 0.10:
        advice.append(f"娯楽費が{entertainment:,}円あります。未使用のゲーム・サブスクを先に確認すると効果的です。")
    fixed = amounts.get("固定費", 0)
    if fixed:
        advice.append(f"固定費は{fixed:,}円です。通信・電気・サブスクは半年ごとに契約内容を見直しましょう。")
    top = categories[0]
    advice.append(f"最大カテゴリは「{top['category']}」の{int(top['amount']):,}円です。まず5%削減で月{int(top['amount'] * 0.05):,}円を目安にできます。")
    return advice[:3]
