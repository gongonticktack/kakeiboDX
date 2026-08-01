"""DB初期化処理のテスト。"""

from unittest.mock import Mock

import pytest

from kakeibo import db


def test_init_schema_creates_database_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """DBが無い場合に作成してからテーブルを作ることを確認する。
    Args:
        monkeypatch: テスト中だけ関数を差し替える仕組み。
    Returns:
        なし。
    """
    calls: list[str] = []

    class FakeConnection:
        """SQL実行だけを記録する接続。
        Args:
            なし。
        Returns:
            なし。
        """

        def execute(self, query: str) -> None:
            """SQL実行を記録する。
            Args:
                query: 実行されたSQL。
            Returns:
                なし。
            """
            calls.append(str(query))

    class FakeDbContext:
        """1回目だけDB未作成エラーにする。
        Args:
            なし。
        Returns:
            なし。
        """

        enter_count = 0

        def __enter__(self) -> FakeConnection:
            """接続開始時の動きを再現する。
            Args:
                なし。
            Returns:
                偽のDB接続。
            """
            FakeDbContext.enter_count += 1
            if FakeDbContext.enter_count == 1:
                raise RuntimeError('database "kakeibo_dx" does not exist')
            return FakeConnection()

        def __exit__(self, *args: object) -> None:
            """終了処理は何もしない。
            Args:
                args: 例外情報。
            Returns:
                なし。
            """
            return None

    created = Mock()
    monkeypatch.setattr(db, "get_db", FakeDbContext)
    monkeypatch.setattr(db, "create_database_if_missing", created)

    db.init_schema()

    created.assert_called_once()
    assert calls


def test_format_connection_error_detects_missing_database() -> None:
    """DB未作成を認証失敗として表示しないことを確認する。
    Args:
        なし。
    Returns:
        なし。
    """
    message = db.format_connection_error(
        RuntimeError('database "kakeibo_dx" does not exist')
    )

    assert "database kakeibo_dx does not exist" in message
