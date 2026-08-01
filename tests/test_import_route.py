"""PDF取込ルートのテスト。"""

from io import BytesIO
from pathlib import Path

from flask import Flask

from kakeibo import create_app
from kakeibo import routes


def test_import_pdf_accepts_multiple_files(monkeypatch, tmp_path: Path) -> None:
    """複数PDFを順番に取り込めることを確認する。
    Args:
        monkeypatch: テスト中だけ関数を差し替える仕組み。
        tmp_path: 一時保存先。
    Returns:
        なし。
    """
    imported_names = []

    def fake_import_statement(path: Path, original_name: str) -> tuple[int, int]:
        """取込対象のファイル名を記録する。
        Args:
            path: 保存済みPDFのパス。
            original_name: アップロード時のファイル名。
        Returns:
            解析件数と保存件数。
        """
        assert path.exists()
        imported_names.append(original_name)
        return 2, 2

    app = create_app({"TESTING": True, "UPLOAD_FOLDER": tmp_path})
    monkeypatch.setattr(routes, "import_statement", fake_import_statement)

    response = app.test_client().post(
        "/import",
        data={
            "statements": [
                (BytesIO(b"pdf-1"), "first.pdf"),
                (BytesIO(b"pdf-2"), "second.pdf"),
            ]
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 302
    assert imported_names == ["first.pdf", "second.pdf"]


def test_import_pdf_accepts_previous_single_file_field(monkeypatch, tmp_path: Path) -> None:
    """古い画面の単一PDF入力名でも取り込めることを確認する。
    Args:
        monkeypatch: テスト中だけ関数を差し替える仕組み。
        tmp_path: 一時保存先。
    Returns:
        なし。
    """
    imported_names = []

    def fake_import_statement(path: Path, original_name: str) -> tuple[int, int]:
        """取込対象のファイル名を記録する。
        Args:
            path: 保存済みPDFのパス。
            original_name: アップロード時のファイル名。
        Returns:
            解析件数と保存件数。
        """
        imported_names.append(original_name)
        return 1, 1

    app = create_app({"TESTING": True, "UPLOAD_FOLDER": tmp_path})
    monkeypatch.setattr(routes, "import_statement", fake_import_statement)

    response = app.test_client().post(
        "/import",
        data={"statement": (BytesIO(b"pdf"), "single.pdf")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 302
    assert imported_names == ["single.pdf"]


def test_import_pdf_skips_non_pdf(monkeypatch, tmp_path: Path) -> None:
    """PDF以外は取り込まないことを確認する。
    Args:
        monkeypatch: テスト中だけ関数を差し替える仕組み。
        tmp_path: 一時保存先。
    Returns:
        なし。
    """
    app: Flask = create_app({"TESTING": True, "UPLOAD_FOLDER": tmp_path})
    monkeypatch.setattr(routes, "import_statement", lambda path, name: (1, 1))

    response = app.test_client().post(
        "/import",
        data={"statements": [(BytesIO(b"text"), "memo.txt")]},
        content_type="multipart/form-data",
    )

    assert response.status_code == 302
    assert not list(tmp_path.iterdir())


def test_import_pdf_keeps_failed_pdf(monkeypatch, tmp_path: Path) -> None:
    """解析に失敗したPDFを調査用に残すことを確認する。
    Args:
        monkeypatch: テスト中だけ関数を差し替える仕組み。
        tmp_path: 一時保存先。
    Returns:
        なし。
    """
    app = create_app({"TESTING": True, "UPLOAD_FOLDER": tmp_path / "uploads"})
    monkeypatch.setattr(routes, "extract_pdf_text", lambda path: "raw extracted text")

    def fail_import(path: Path, original_name: str) -> tuple[int, int]:
        """取込失敗を再現する。
        Args:
            path: 保存済みPDFのパス。
            original_name: アップロード時のファイル名。
        Returns:
            使わない戻り値。
        """
        raise ValueError("利用明細を読み取れませんでした。")

    monkeypatch.setattr(routes, "import_statement", fail_import)

    response = app.test_client().post(
        "/import",
        data={"statements": [(BytesIO(b"broken-pdf"), "broken.pdf")]},
        content_type="multipart/form-data",
    )

    assert response.status_code == 302
    assert not list((tmp_path / "uploads").glob("*.pdf"))
    assert len(list((tmp_path / "failed_uploads").glob("*_broken.pdf"))) == 1
    reports = list((tmp_path / "failed_uploads").glob("*_broken.txt"))
    assert len(reports) == 1
    assert "raw extracted text" in reports[0].read_text(encoding="utf-8")


def test_add_manual_transaction_route(monkeypatch, tmp_path: Path) -> None:
    """手動入力フォームから明細を追加できることを確認する。
    Args:
        monkeypatch: テスト中だけ関数を差し替える仕組み。
        tmp_path: 一時保存先。
    Returns:
        なし。
    """
    saved = {}

    def fake_add_manual_transaction(used_at, merchant, amount, category, payment_method):
        """保存内容を記録する。
        Args:
            used_at: 利用日時。
            merchant: 内容。
            amount: 金額。
            category: カテゴリ。
            payment_method: 支払方法。
        Returns:
            偽の明細ID。
        """
        saved.update(
            {
                "used_at": used_at,
                "merchant": merchant,
                "amount": amount,
                "category": category,
                "payment_method": payment_method,
            }
        )
        return 1

    app = create_app({"TESTING": True, "UPLOAD_FOLDER": tmp_path})
    monkeypatch.setattr(routes, "add_manual_transaction", fake_add_manual_transaction)

    response = app.test_client().post(
        "/manual",
        data={
            "used_on": "2026-06-30",
            "merchant": "現金ランチ",
            "amount": "980",
            "category": "食費",
            "payment_method": "現金",
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/?period=month&value=2026-06")
    assert saved["merchant"] == "現金ランチ"
    assert saved["amount"] == 980
    assert saved["category"] == "食費"
    assert saved["payment_method"] == "現金"


def test_add_manual_transaction_rejects_invalid_category(monkeypatch, tmp_path: Path) -> None:
    """不正なカテゴリでは保存しないことを確認する。
    Args:
        monkeypatch: テスト中だけ関数を差し替える仕組み。
        tmp_path: 一時保存先。
    Returns:
        なし。
    """
    app = create_app({"TESTING": True, "UPLOAD_FOLDER": tmp_path})
    called = False

    def fake_add_manual_transaction(*args):
        """呼ばれたら失敗にする。
        Args:
            args: 保存引数。
        Returns:
            なし。
        """
        nonlocal called
        called = True

    monkeypatch.setattr(routes, "add_manual_transaction", fake_add_manual_transaction)

    response = app.test_client().post(
        "/manual",
        data={
            "used_on": "2026-06-30",
            "merchant": "現金ランチ",
            "amount": "980",
            "category": "不正",
        },
    )

    assert response.status_code == 302
    assert not called


def test_update_category_can_apply_to_similar_items(monkeypatch, tmp_path: Path) -> None:
    """チェックありなら似た店舗名へカテゴリ変更を反映する。
    Args:
        monkeypatch: テスト中だけ関数を差し替える仕組み。
        tmp_path: 一時保存先。
    Returns:
        なし。
    """
    called = {}

    def fake_remember_category_for_transaction(transaction_id: int, category: str) -> int:
        """学習あり更新の呼び出しを記録する。
        Args:
            transaction_id: 更新対象ID。
            category: 変更後カテゴリ。
        Returns:
            更新件数。
        """
        called["remember"] = (transaction_id, category)
        return 3

    def fake_update_single_transaction_category(transaction_id: int, category: str) -> int:
        """単独更新が呼ばれていないことを確認するための関数。
        Args:
            transaction_id: 更新対象ID。
            category: 変更後カテゴリ。
        Returns:
            更新件数。
        """
        called["single"] = (transaction_id, category)
        return 1

    app = create_app({"TESTING": True, "UPLOAD_FOLDER": tmp_path})
    monkeypatch.setattr(routes, "remember_category_for_transaction", fake_remember_category_for_transaction)
    monkeypatch.setattr(routes, "update_single_transaction_category", fake_update_single_transaction_category)

    response = app.test_client().post(
        "/transactions/42/category",
        data={"category": "食費", "apply_similar": "1"},
    )

    assert response.status_code == 302
    assert called["remember"] == (42, "食費")
    assert "single" not in called


def test_update_category_can_change_only_one_item(monkeypatch, tmp_path: Path) -> None:
    """チェックなしならその明細だけカテゴリ変更する。
    Args:
        monkeypatch: テスト中だけ関数を差し替える仕組み。
        tmp_path: 一時保存先。
    Returns:
        なし。
    """
    called = {}

    def fake_remember_category_for_transaction(transaction_id: int, category: str) -> int:
        """学習あり更新が呼ばれていないことを確認するための関数。
        Args:
            transaction_id: 更新対象ID。
            category: 変更後カテゴリ。
        Returns:
            更新件数。
        """
        called["remember"] = (transaction_id, category)
        return 3

    def fake_update_single_transaction_category(transaction_id: int, category: str) -> int:
        """単独更新の呼び出しを記録する。
        Args:
            transaction_id: 更新対象ID。
            category: 変更後カテゴリ。
        Returns:
            更新件数。
        """
        called["single"] = (transaction_id, category)
        return 1

    app = create_app({"TESTING": True, "UPLOAD_FOLDER": tmp_path})
    monkeypatch.setattr(routes, "remember_category_for_transaction", fake_remember_category_for_transaction)
    monkeypatch.setattr(routes, "update_single_transaction_category", fake_update_single_transaction_category)

    response = app.test_client().post(
        "/transactions/42/category",
        data={"category": "食費"},
    )

    assert response.status_code == 302
    assert called["single"] == (42, "食費")
    assert "remember" not in called
