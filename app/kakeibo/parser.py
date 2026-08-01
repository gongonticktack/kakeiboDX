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
    (
        "税金",
        (
            "地方税共同機構", "ELTAX", "国税", "税務署", "都税", "県税", "府税",
            "市税", "住民税", "固定資産税", "自動車税", "軽自動車税", "納税",
            "市役所", "区役所", "シヤクシヨ", "クヤクシヨ", "奈良県", "大阪府",
        ),
    ),
    (
        "資産形成",
        (
            "証券", "投信積立", "NISA", "IDECO", "SBI SECURITIES", "RAKUTEN SEC", "楽天証券",
            "マネックス", "MONEX", "松井証券", "カブコム", "大和証券", "野村證券",
        ),
    ),
    (
        "固定費",
        (
            "中部電力", "東京電力", "関西電力", "大阪ガス", "東京ガス", "水道", "電気",
            "上下水道", "ジヨウゲスイドウ", "エルピオ", "ELPIO", "生命保険", "損害保険",
            "マニュライフ", "三井ダイレクト", "アマゾンプライム",
            "モバイル通信", "ドコモ", "DOCOMO", "AU", "KDDI", "SOFTBANK", "Y!MOBILE",
            "UQ MOBILE", "RAKUTEN MOBILE", "楽天モバイル", "MINEO", "IIJ", "OCN",
            "ぷらら", "NURO", "BIGLOBE", "J:COM", "NHK", "家賃", "管理費",
            "CHATGPT SUBS", "OPENAI", "GOOGLE STORAGE", "ICLOUD", "DROPBOX",
            "MICROSOFT", "マイクロソフト", "ADOBE", "AMAZON PRIME",
        ),
    ),
    (
        "交通",
        (
            "SUICA", "PASMO", "ICOCA", "MANACA", "TOICA", "SUGOCA", "KITACA", "NIMOCA",
            "はやかけん", "チャージ", "JR", "JRE", "東京メトロ", "名鉄", "近鉄", "阪急",
            "阪神", "京王", "小田急", "東急", "西鉄", "タクシー", "TAXI", "UBER TRIP",
            "GO タクシー", "高速道路", "ETC", "駐車場", "PARKING", "タイムズ",
            "スマートEX", "スマートイーエックス", "スマ-トイ-エツクス", "RAINBOW BRIDGE",
            "NEXCO", "ネクスコ", "SAPA", "空港", "セントレア", "APPLE PA",
            "ENEOS", "イエローハット", "クロネコヤマト", "ヤマトウンユ", "ニツポンユウビン",
        ),
    ),
    (
        "医療・健康",
        (
            "薬局", "ﾔﾂｷﾖｸ", "ドラッグ", "DRUG", "マツモトキヨシ", "ウエルシア",
            "スギ薬局", "ツルハ", "ココカラファイン", "サンドラッグ", "クリエイト",
            "ヘルスケア", "メディカル", "病院", "医院", "クリニック", "歯科",
            "ビヨウイン", "シカ ", "シカクリニ", "クリニツク", "整体", "接骨", "整骨", "ジム", "FITNESS",
            "ANYTIME", "CHOCOLAP", "アイハーブ", "IHERB", "デイ-ラボ", "ダイコクドラツグ",
            "アインファーマシーズ", "ケンコウセンター", "ケンコウセンタ-", "ウエルボツクス",
            "アマノアプリ",
        ),
    ),
    (
        "自己投資",
        (
            "UDEMY", "VUE*TESTING", "電子書籍", "KOBO", "KINDLE", "BOOKWALKER",
            "書店", "紀伊國屋", "丸善", "ジュンク堂", "資格", "受験", "試験", "検定",
            "TOEIC", "CBTS", "シービーティーエス", "プロメトリック", "プロジエクトマネ",
            "COURSERA", "EDX", "LINKEDIN LEARNING", "PROGATE", "ドットインストール",
            "楽天ブックス", "ブックオフ公式オンラインストア", "BOOKOFF", "ブツクオフ",
            "ブックオフ", "BOOKFAN", "スタディサプリ", "スタデイサプリ", "ネットオフ",
        ),
    ),
    (
        "娯楽",
        (
            "STEAM", "GOOGLE PLAY", "NINTENDO", "PLAYSTATION", "PSN", "XBOX",
            "第一興商", "カラオケ", "映画", "シネマ", "TOHO", "イオンシネマ",
            "NETFLIX", "HULU", "DISNEY", "U-NEXT", "SPOTIFY", "AWA", "APPLE MUSIC",
            "DMM", "DLsite", "BOOKLIVE", "チケット", "TICKET", "ライブ", "コンサート",
            "名古屋城", "ナゴヤジョウ", "ゴルフ", "GOLF", "カントリー倶楽部",
            "カントリークラブ", "アコ-デイア", "快活クラブ", "マンボー", "マンボ-", "まねきねこ",
            "JOYSOUND", "ジヨイサウンド", "まんが喫茶", "イベント", "バンダイ",
            "BOOTH", "キネン",
        ),
    ),
    (
        "衣服・美容",
        (
            "ジーユー", "GU", "ユニクロ", "UNIQLO", "しまむら", "ZOZOTOWN", "ZOZO",
            "H&M", "ZARA", "無印良品", "MUJI", "ABC-MART", "ABC MART", "HAERA",
            "ﾗﾊﾟﾝ", "WORLD NEXT", "美容", "理容", "ヘア", "HAIR", "サロン", "NAIL",
            "ネイル", "コスメ", "COSME", "ロクシタン", "L'OCCITANE", "アンド ハビット",
            "スタジオインデイ", "おむつケーキ", "ベビーアニヴェ",
        ),
    ),
    (
        "日用品",
        (
            "AMAZON", "楽天市場", "RAKUTEN ICHIBA", "YAHOO!ショッピング", "ヨドバシ",
            "ビックカメラ", "BIC CAMERA", "ケーズデンキ", "エディオン", "ヤマダデンキ",
            "ニトリ", "IKEA", "カインズ", "DCM", "コーナン", "コメリ", "ホームセンター",
            "ダイソー", "DAISO", "セリア", "SERIA", "キャンドゥ", "ロフト", "LOFT",
            "東急ハンズ", "ハンズ", "無印良品", "MUJI", "HMK TOOLS", "RENTIO",
            "レンテイオ", "楽天ペイ加盟店アプリ", "CHARGESPOT", "パナソニックストアプラス",
            "パナソニツクストアプラス", "TOKYO INTERIOR", "BRUNO", "ドンキホーテ",
            "DONKI", "キユ-テン", "QOO10", "ビツクカメラ", "デイ-シ-エム",
            "ト-キヨ-インテリア", "ムジルシリヨウヒン", "アルペン", "ラインイ-シ-",
            "インフオリツチ",
        ),
    ),
    (
        "食費",
        (
            "イオン", "ｲｵﾝ", "フイ-ル", "ﾌｲ-ﾙ", "セブン", "ファミリーマート", "マクドナルド",
            "なか卯", "松屋", "ナッシュ", "ﾅｯｼｭ", "スシロー", "焼肉", "コメダ", "ゴンチャ",
            "壱番屋", "ミスタードーナツ", "UBER EATS", "ベントマン", "ｳｵﾂﾊﾞｷ", "ﾄｷｼｶ",
            "プレミアムウオーター", "ﾌﾟﾚﾐｱﾑｳｵ-ﾀ-", "ジハンピ", "ローソン", "LAWSON",
            "セブン-イレブン", "7-ELEVEN", "ファミマ", "FAMIMA", "ミニストップ",
            "MINISTOP", "デイリーヤマザキ", "スーパー", "マックスバリュ", "MAXVALU",
            "西友", "SEIYU", "ライフ", "LIFE", "バロー", "VALOR", "ヤオコー",
            "イトーヨーカドー", "業務スーパー", "コストコ", "COSTCO", "ドミノピザ",
            "PIZZA", "ケンタッキー", "KFC", "モスバーガー", "MOS BURGER",
            "バーガーキング", "BURGER KING", "すき家", "吉野家", "はま寿司", "くら寿司",
            "餃子の王将", "サイゼリヤ", "ガスト", "ジョナサン", "デニーズ", "スターバックス",
            "STARBUCKS", "ドトール", "DOUTOR", "タリーズ", "TULLY", "出前館", "WOLT",
            "名古屋駅店舗アプリ", "アンバタ", "ナゴヤノモノ", "デイリーヤマザキ",
            "一蘭", "ミニストップ", "サトフードサービス", "元気寿司", "NOSH",
            "マルツトウオーター", "ワイストア", "ヤマナカ", "フランテ", "牛角",
            "ギユウカク", "チバチヤン", "ルピシア", "コノミヤ", "スキヤ", "すき家",
            "トヨタ自動車本館売店", "駅構内店舗", "ファーストキッチン", "ナカウ",
            "ウオベイ", "魚べい", "ベーカリー", "ベ-カ-", "サカヤビツク", "ヨシノヤ",
            "やよい軒", "ヨークマート", "ラ-メン", "らあめん", "ゼツテリア",
            "スタ-バツクス", "ほっともっと", "スガキコ", "自販機", "キリンビバレッジ",
            "IJOOZ", "ペリエ千葉", "セントラルパーク", "ホンシヤチユウオウバイテン",
            "プラスタ", "プラスタギフト", "ヨシヅヤ", "スシマル", "ピザハット",
            "自動販売機", "NEW DAYS", "NEWDAYS", "FEEL", "マツクスバリユ",
            "東京駅グランスタ", "エリツクサウス", "ナゴヤエキテンポ",
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
