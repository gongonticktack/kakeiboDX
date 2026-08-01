"""楽天カードPDFから利用明細を抽出する。"""

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pdfplumber


@dataclass(frozen=True)
class ParsedTransaction:
    """PDFから読み取った1件の利用明細。"""

    used_at: datetime
    merchant: str
    amount: int
    category: str
    payment_method: str
    source_hash: str


CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("資産形成", ("証券", "投信積立")),
    ("固定費", ("中部電力", "モバイル通信", "ドコモ", "ぷらら", "CHATGPT SUBS")),
    ("交通", ("SUICA", "チャージ")),
    ("医療・健康", ("薬局", "ﾔﾂｷﾖｸ", "マツモトキヨシ", "ヘルスケア", "メディカル")),
    ("自己投資", ("UDEMY", "VUE*TESTING", "電子書籍", "KOBO")),
    ("娯楽", ("STEAM", "GOOGLE PLAY", "第一興商")),
    ("衣服・美容", ("ジーユー", "HAERA", "ﾗﾊﾟﾝ", "WORLD NEXT")),
    ("日用品", ("AMAZON", "ケーズデンキ", "ダイソー", "セリア", "ロフト", "HMK TOOLS", "RENTIO")),
    (
        "食費",
        (
            "イオン", "ｲｵﾝ", "フイ-ル", "ﾌｲ-ﾙ", "セブン", "ファミリーマート", "マクドナルド",
            "なか卯", "松屋", "ナッシュ", "ﾅｯｼｭ", "スシロー", "焼肉", "コメダ", "ゴンチャ",
            "壱番屋", "ミスタードーナツ", "UBER EATS", "ベントマン", "ｳｵﾂﾊﾞｷ", "ﾄｷｼｶ",
            "プレミアムウオーター", "ﾌﾟﾚﾐｱﾑｳｵ-ﾀ-", "ジハンピ",
        ),
    ),
)

ROW_PATTERNS = (
    re.compile(
        r"^(?P<date>\d{4}/\d{2}/\d{2})\s+"
        r"(?P<merchant>.+?)\s+本人\*?\s+"
        r"(?P<payment>\S+払い)\s+"
        r"(?P<amount>[\d,]+)円?\s+"
        r"(?:-?[\d,]+円?\s+){4}-?[\d,]+円?$"
    ),
    re.compile(
        r"^(?P<date>\d{4}/\d{2}/\d{2})\s+"
        r"(?P<merchant>.+?)\s+"
        r"(?P<payment>\S+払い)\s+"
        r"(?P<amount>[\d,]+)円?\s+"
        r"(?:-?[\d,]+円?\s+){4}-?[\d,]+円?$"
    ),
)
PAYMENT_PATTERN = re.compile(r"\S+払い")
AMOUNT_PATTERN = re.compile(r"-?[\d,]+円?")


def normalize_merchant(value: str) -> str:
    """店舗名の空白と全半角を整える。

    Args:
        value: PDFから抽出した店舗名。

    Returns:
        整形済み店舗名。
    """
    normalized = unicodedata.normalize("NFKC", value)
    return re.sub(r"\s+", " ", normalized).strip()


def categorize(merchant: str) -> str:
    """店舗名からカテゴリを推定する。

    Args:
        merchant: 整形済み店舗名。

    Returns:
        推定カテゴリ名。
    """
    target = merchant.upper()
    for category, keywords in CATEGORY_RULES:
        if any(unicodedata.normalize("NFKC", keyword).upper() in target for keyword in keywords):
            return category
    return "その他"


def normalize_pdf_line(line: str) -> str:
    """PDFの1行を比較しやすい形へ整える。

    Args:
        line: PDFから抽出した1行。

    Returns:
        全角半角と空白をそろえた文字列。
    """
    # PDFごとの全角・半角の揺れを先にそろえる。
    normalized = unicodedata.normalize("NFKC", line)
    return re.sub(r"\s+", " ", normalized).strip()


def parse_amount(value: str) -> int:
    """金額文字列を整数へ変換する。

    Args:
        value: PDFから抽出した金額文字列。

    Returns:
        円単位の金額。
    """
    normalized = unicodedata.normalize("NFKC", value)
    digits = normalized.replace(",", "").replace("円", "")
    return abs(int(digits))


def parse_transaction_line(line: str) -> tuple[datetime, str, int, str] | None:
    """PDFの1行から明細の基本項目を読み取る。

    Args:
        line: PDFから抽出した1行。

    Returns:
        日付、店舗名、金額、支払方法。明細行でなければNone。
    """
    stripped = normalize_pdf_line(line)
    for pattern in ROW_PATTERNS:
        match = pattern.match(stripped)
        if match:
            return (
                datetime.strptime(match["date"], "%Y/%m/%d"),
                normalize_merchant(match["merchant"]),
                parse_amount(match["amount"]),
                match["payment"],
            )
    date_match = re.match(r"^(?P<date>\d{4}/\d{2}/\d{2})\s+(?P<body>.+)$", stripped)
    if not date_match:
        return None
    body = date_match["body"]
    payment_match = PAYMENT_PATTERN.search(body)
    if not payment_match:
        return None
    amount_match = AMOUNT_PATTERN.search(body, payment_match.end())
    if not amount_match:
        return None
    merchant = body[: payment_match.start()].replace("本人*", "").replace("本人", "")
    merchant = normalize_merchant(merchant)
    if not merchant:
        return None
    return (
        datetime.strptime(date_match["date"], "%Y/%m/%d"),
        merchant,
        parse_amount(amount_match.group(0)),
        payment_match.group(0),
    )


def parse_text(text: str) -> list[ParsedTransaction]:
    """抽出済みPDFテキストを明細へ変換する。

    Args:
        text: PDF全ページのテキスト。

    Returns:
        読み取れた利用明細の一覧。
    """
    results: list[ParsedTransaction] = []
    for line in text.splitlines():
        parsed = parse_transaction_line(line)
        if not parsed:
            continue
        used_at, merchant, amount, payment = parsed
        identity = f"{used_at.isoformat()}|{merchant}|{amount}|{payment}"
        results.append(
            ParsedTransaction(
                used_at=used_at,
                merchant=merchant,
                amount=amount,
                category=categorize(merchant),
                payment_method=payment,
                source_hash=hashlib.sha256(identity.encode("utf-8")).hexdigest(),
            )
        )
    return results


def extract_pdf_text(path: str | Path) -> str:
    """PDFからテキストを抽出する。

    Args:
        path: 読み取るPDFのパス。

    Returns:
        全ページから抽出したテキスト。
    """
    with pdfplumber.open(path) as pdf:
        return "\n".join(
            page.extract_text(x_tolerance=2, y_tolerance=3) or ""
            for page in pdf.pages
        )


def parse_pdf(path: str | Path) -> tuple[list[ParsedTransaction], datetime | None]:
    """楽天カード明細PDFを読み取る。

    Args:
        path: 読み取るPDFのパス。

    Returns:
        利用明細一覧と明細発行日時。
    """
    text = extract_pdf_text(path)
    statement_match = re.search(r"(\d{4})/(\d{2})/(\d{2})", text[:500])
    statement_date = (
        datetime.strptime(statement_match.group(0), "%Y/%m/%d")
        if statement_match
        else None
    )
    return parse_text(text), statement_date
