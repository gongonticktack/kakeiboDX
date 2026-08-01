"""PDF明細パーサーのテスト。"""

import pytest

from kakeibo.parser import categorize, parse_text


def test_parse_rakuten_row() -> None:
    """楽天カードの1行を必要項目へ変換できることを確認する。"""
    text = "2026/06/29 AMAZON.CO.JP 本人* 1回払い 2,160 0 2,160 2,160 2,160 0"
    rows = parse_text(text)
    assert len(rows) == 1
    assert rows[0].amount == 2160
    assert rows[0].merchant == "AMAZON.CO.JP"
    assert rows[0].category == "日用品"


def test_parse_rakuten_row_without_user_column() -> None:
    """利用者列が無い古い明細行も読み取れることを確認する。
    Args:
        なし。
    Returns:
        なし。
    """
    text = "2025/04/29 AMAZON.CO.JP 1回払い 2,160 0 2,160 2,160 2,160 0"
    rows = parse_text(text)
    assert len(rows) == 1
    assert rows[0].amount == 2160
    assert rows[0].merchant == "AMAZON.CO.JP"
    assert rows[0].payment_method == "1回払い"


def test_parse_rakuten_row_with_full_width_numbers_and_yen() -> None:
    """全角数字や円付き金額の明細行も読み取れることを確認する。
    Args:
        なし。
    Returns:
        なし。
    """
    text = "２０２５/０４/２９ AMAZON.CO.JP 本人* １回払い ２,１６０円 ０円 ２,１６０円 ２,１６０円 ２,１６０円 ０円"
    rows = parse_text(text)
    assert len(rows) == 1
    assert rows[0].used_at.strftime("%Y/%m/%d") == "2025/04/29"
    assert rows[0].amount == 2160
    assert rows[0].payment_method == "1回払い"


def test_parse_rakuten_row_with_short_amount_columns() -> None:
    """後ろの金額列が少ない明細行も読み取れることを確認する。
    Args:
        なし。
    Returns:
        なし。
    """
    text = "2025/05/10 楽天ＳＰ セブン－イレブン 本人* 1回払い 870 0 870"
    rows = parse_text(text)
    assert len(rows) == 1
    assert rows[0].merchant == "楽天SP セブン-イレブン"
    assert rows[0].amount == 870


def test_parse_rakuten_row_with_amount_columns_after_payment_only() -> None:
    """支払方法直後の利用金額を優先して読み取れることを確認する。
    Args:
        なし。
    Returns:
        なし。
    """
    text = "2025/05/10 AMAZON.CO.JP 1回払い 2,160 2,160"
    rows = parse_text(text)
    assert len(rows) == 1
    assert rows[0].amount == 2160


def test_categorize_food() -> None:
    """コンビニ利用を食費と判定できることを確認する。"""
    assert categorize("楽天SP 楽天ペイセブン-イレブン") == "食費"


@pytest.mark.parametrize(
    ("merchant", "expected"),
    [
        ("OPENAI *CHATGPT SUBSCRIPTION", "固定費"),
        ("SBI SECURITIES 投信積立", "資産形成"),
        ("JR東日本 SUICAチャージ", "交通"),
        ("ウエルシア薬局", "医療・健康"),
        ("紀伊國屋書店 電子書籍", "自己投資"),
        ("NETFLIX.COM", "娯楽"),
        ("ZOZOTOWN", "衣服・美容"),
        ("ヨドバシカメラ", "日用品"),
        ("STARBUCKS COFFEE", "食費"),
        ("楽天SP 名古屋駅店舗アプリ", "食費"),
        ("楽天SP 楽天ペイ加盟店アプリ", "日用品"),
        ("ユ-クオンペイ/APPLE PA", "交通"),
        ("アンバタハナゴヤノモノ ナコ", "食費"),
        ("エルピオ", "固定費"),
        ("ナゴヤジョウグッズバイウキ", "娯楽"),
        ("楽天SP デイリーヤマザキアプリ", "食費"),
        ("ChargeSPOT", "日用品"),
        ("マニュライフセイメイホケンリョウ", "固定費"),
        ("地方税共同機構(eLTAX)", "税金"),
        ("国税クレジットカード納付", "税金"),
        ("スマ-トイ-エツクス ジエイア-", "交通"),
        ("ナゴヤシジヨウゲスイドウキ", "固定費"),
        ("シービーティーエスジュケンモウ", "自己投資"),
        ("タテベシカクリニツク", "医療・健康"),
        ("アコ-デイア.ガ-デンナゴ", "娯楽"),
        ("AMZ*ト-キヨ-インテリア", "日用品"),
        ("楽天SP NewDaysアプリ", "食費"),
        ("楽天ブックス", "自己投資"),
        ("楽天SP 一蘭アプリ", "食費"),
        ("楽天SP ミニストップ", "食費"),
        ("楽天SP サトフードサービス", "食費"),
        ("パナソニックストアプラスナゴツ", "日用品"),
        ("楽天SP 元気寿司", "食費"),
        ("Rainbow Bridge", "交通"),
        ("スタディサプリイングリッシュ", "自己投資"),
        ("ブックオフ公式オンラインストア", "自己投資"),
        ("TOKYO interior", "日用品"),
        ("スマートイーエックス ジェイアー", "交通"),
    ],
)
def test_categorize_common_merchants(merchant: str, expected: str) -> None:
    """よく出る加盟店名を代表カテゴリへ分類できることを確認する。

    Args:
        merchant: 分類する加盟店名。
        expected: 期待するカテゴリ名。

    Returns:
        なし。
    """
    assert categorize(merchant) == expected


def test_ignore_non_transaction_line() -> None:
    """表の見出しや注記を明細にしないことを確認する。"""
    assert parse_text("ご利用代金請求明細書") == []
