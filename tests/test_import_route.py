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
