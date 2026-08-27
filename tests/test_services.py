"""明細保存サービスのテスト。"""

from datetime import datetime

from kakeibo.parser import ParsedTransaction
from kakeibo.services import (
    build_average_comparison,
    build_average_insights,
    build_advice,
    floor_to_hundreds,
    group_transactions,
    merchant_key,
    normalize_period_value,
    period_navigation,
    safe_year,
    safe_year_month,
    shift_period_value,
    similar_merchant_key,
    transaction_match_counts,
    transaction_source_hash,
)


def test_group_transactions_sums_same_merchants() -> None:
    """同じ利用会社の金額と件数をまとめられることを確認する。
    Args:
        なし。
    Returns:
        なし。
    """
    rows = [
        {"id": 1, "used_at": datetime(2026, 8, 1), "merchant": "スーパー 東店", "amount": 800, "category": "食費"},
        {"id": 2, "used_at": datetime(2026, 8, 2), "merchant": "スーパー 西店", "amount": 1200, "category": "食費"},
        {"id": 3, "used_at": datetime(2026, 8, 3), "merchant": "書店", "amount": 500, "category": "娯楽"},
    ]

    grouped = group_transactions(rows, "amount", "desc")

    assert grouped[0]["merchant"] == "スーパー"
    assert grouped[0]["amount"] == 2000
    assert grouped[0]["count"] == 2


def test_group_transactions_marks_mixed_categories() -> None:
    """同じ利用会社でカテゴリが混在する場合を表示できることを確認する。
    Args:
        なし。
    Returns:
        なし。
    """
    rows = [
        {"id": 1, "used_at": datetime(2026, 8, 1), "merchant": "店舗", "amount": 800, "category": "食費"},
        {"id": 2, "used_at": datetime(2026, 8, 2), "merchant": "店舗", "amount": 1200, "category": "日用品"},
    ]

    grouped = group_transactions(rows, "date", "desc")

    assert grouped[0]["category"] == "複数"


def test_transaction_source_hash_uses_row_index() -> None:
    """同じ内容の明細でもPDF内の別行なら別ハッシュにする。
    Args:
        なし。
    Returns:
        なし。
    """
    item = ParsedTransaction(
        used_at=datetime(2025, 5, 10),
        merchant="AMAZON.CO.JP",
        amount=2160,
        category="日用品",
        payment_method="1回払い",
        source_hash="old",
    )

    first_hash = transaction_source_hash("file-hash", 1, item)
    second_hash = transaction_source_hash("file-hash", 2, item)

    assert first_hash != second_hash


def test_transaction_match_counts_preserves_duplicate_rows() -> None:
    """同じ内容の明細が複数あることを件数として残す。
    Args:
        なし。
    Returns:
        なし。
    """
    item = ParsedTransaction(
        used_at=datetime(2025, 5, 10),
        merchant="AMAZON.CO.JP",
        amount=2160,
        category="日用品",
        payment_method="1回払い",
        source_hash="old",
    )

    counts = transaction_match_counts([item, item])

    assert counts[(item.used_at, item.merchant, item.amount, item.payment_method)] == 2


def test_merchant_key_normalizes_similar_names() -> None:
    """似た店舗名が同じキーになることを確認する。
    Args:
        なし。
    Returns:
        なし。
    """
    assert merchant_key("楽天ＳＰ セブン－イレブン") == merchant_key("楽天SP セブン-イレブン")


def test_similar_merchant_key_matches_contained_names() -> None:
    """名前の一部が共通する店舗を似たものとして扱う。
    Args:
        なし。
    Returns:
        なし。
    """
    base = merchant_key("楽天SP ファミリーマートアプリ")
    target = merchant_key("楽天SP ファミリーマートアプリ 本山駅前")

    assert similar_merchant_key(base, target)


def test_shift_period_value_moves_month_across_year() -> None:
    """月移動で年またぎできることを確認する。
    Args:
        なし。
    Returns:
        なし。
    """
    assert shift_period_value("month", "2026-01", -1) == "2025-12"
    assert shift_period_value("month", "2026-12", 1) == "2027-01"


def test_shift_period_value_moves_year() -> None:
    """年移動できることを確認する。
    Args:
        なし。
    Returns:
        なし。
    """
    assert shift_period_value("year", "2026", -1) == "2025"
    assert shift_period_value("year", "2026", 1) == "2027"


def test_shift_period_value_ignores_invalid_month_value() -> None:
    """壊れた月指定でも期間移動でエラーにしないことを確認する。
    Args:
        なし。
    Returns:
        なし。
    """
    shifted = shift_period_value("month", "2026", 1)

    assert shifted.count("-") == 1


def test_safe_period_values_fallback_for_invalid_input() -> None:
    """URLの不正な期間値を既定値へ戻せることを確認する。
    Args:
        なし。
    Returns:
        なし。
    """
    assert safe_year("not-a-year") == datetime.today().year
    assert safe_year_month("2026") == (datetime.today().year, datetime.today().month)
    assert safe_year_month("2026-99") == (datetime.today().year, datetime.today().month)
    assert normalize_period_value("month", "2026").count("-") == 1


def test_period_navigation_is_hidden_for_all() -> None:
    """累計では期間移動を出さないことを確認する。
    Args:
        なし。
    Returns:
        なし。
    """
    assert period_navigation("all", None) is None


def test_build_average_insights_detects_high_monthly_category() -> None:
    """月平均よりかなり多いカテゴリを指摘できることを確認する。
    Args:
        なし。
    Returns:
        なし。
    """
    insights = build_average_insights("month", [{"category": "食費", "amount": 60000}])

    assert "食費" in insights[0]
    assert "多め" in insights[0]
    assert "43,900円" in insights[0]
    assert "16,059円多め" in insights[0]


def test_build_average_insights_uses_yearly_average() -> None:
    """年表示では平均値を12倍して比べることを確認する。
    Args:
        なし。
    Returns:
        なし。
    """
    insights = build_average_insights("year", [{"category": "食費", "amount": 100000}])

    assert "大きく超えているカテゴリは見つかりません" in insights[0]


def test_build_average_insights_skips_all_period() -> None:
    """累計では平均比較を出さないことを確認する。
    Args:
        なし。
    Returns:
        なし。
    """
    insights = build_average_insights("all", [{"category": "食費", "amount": 60000}])

    assert "月表示または年表示" in insights[0]


def test_build_average_comparison_uses_rounded_average_and_exact_difference() -> None:
    """平均比較グラフ用データは平均だけ丸めて差額は実額にする。
    Args:
        なし。
    Returns:
        なし。
    """
    rows = build_average_comparison("month", [{"category": "食費", "amount": 60000}])
    food = next(row for row in rows if row["category"] == "食費")

    assert food["average"] == 43900
    assert food["difference"] == 16059


def test_build_average_comparison_skips_excluded_categories_and_all_period() -> None:
    """投資系カテゴリと累計表示を平均比較グラフから外す。
    Args:
        なし。
    Returns:
        なし。
    """
    rows = build_average_comparison(
        "month",
        [
            {"category": "自己投資", "amount": 100000},
            {"category": "資産形成", "amount": 100000},
        ],
    )

    assert all(row["category"] not in {"自己投資", "資産形成"} for row in rows)
    assert build_average_comparison("all", [{"category": "食費", "amount": 60000}]) == []


def test_floor_to_hundreds_rounds_down() -> None:
    """100円未満を切り捨てることを確認する。
    Args:
        なし。
    Returns:
        なし。
    """
    assert floor_to_hundreds(43941) == 43900


def test_build_advice_includes_daily_goods_tip() -> None:
    """日用品が多い時の助言を出せることを確認する。
    Args:
        なし。
    Returns:
        なし。
    """
    advice = build_advice(
        [
            {"category": "日用品", "amount": 20000},
            {"category": "食費", "amount": 30000},
        ],
        100000,
    )

    assert any("日用品" in item for item in advice)


def test_build_advice_limits_to_three_items() -> None:
    """助言が増えても画面では3件までにすることを確認する。
    Args:
        なし。
    Returns:
        なし。
    """
    advice = build_advice(
        [
            {"category": "食費", "amount": 60000},
            {"category": "日用品", "amount": 30000},
            {"category": "娯楽", "amount": 25000},
            {"category": "固定費", "amount": 40000},
        ],
        150000,
    )

    assert len(advice) == 3


def test_average_insights_skip_self_investment_categories() -> None:
    """自己投資や資産形成を平均超過の指摘から外すことを確認する。
    Args:
        なし。
    Returns:
        なし。
    """
    insights = build_average_insights(
        "month",
        [
            {"category": "自己投資", "amount": 100000},
            {"category": "資産形成", "amount": 100000},
        ],
    )

    assert "大きく超えているカテゴリは見つかりません" in insights[0]


def test_build_advice_skips_self_investment_tip() -> None:
    """自己投資が多くても節約助言にしないことを確認する。
    Args:
        なし。
    Returns:
        なし。
    """
    advice = build_advice(
        [
            {"category": "自己投資", "amount": 90000},
            {"category": "食費", "amount": 10000},
        ],
        100000,
    )

    assert all("自己投資" not in item for item in advice)
