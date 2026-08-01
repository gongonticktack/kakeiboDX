"""明細保存サービスのテスト。"""

from datetime import datetime

from kakeibo.parser import ParsedTransaction
from kakeibo.services import transaction_match_counts, transaction_source_hash


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
