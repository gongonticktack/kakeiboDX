"""PDF明細パーサーのテスト。"""

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


def test_ignore_non_transaction_line() -> None:
    """表の見出しや注記を明細にしないことを確認する。"""
    assert parse_text("ご利用代金請求明細書") == []
