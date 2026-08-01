"""アプリ起動処理のテスト。"""

from unittest.mock import patch

import pytest

from kakeibo.__main__ import choose_port, display_url, local_ip_address, open_browser_later


def test_open_browser_later_starts_timer() -> None:
    """ブラウザ起動タイマーが開始されることを確認する。
    Args:
        なし。
    Returns:
        なし。
    """
    with patch("kakeibo.__main__.threading.Timer") as timer:
        open_browser_later("http://127.0.0.1:5050")
        timer.assert_called_once()
        timer.return_value.start.assert_called_once()


def test_choose_port_keeps_configured_port() -> None:
    """固定ポート指定時はその番号を使うことを確認する。
    Args:
        なし。
    Returns:
        なし。
    """
    assert choose_port(5050) == 5050


def test_choose_port_requires_configured_port() -> None:
    """未設定のままでは起動しないことを確認する。
    Args:
        なし。
    Returns:
        なし。
    """
    with pytest.raises(ValueError):
        choose_port(None)


def test_display_url_uses_local_ip_for_all_interfaces(monkeypatch) -> None:
    """全インターフェース待受時は自身のIPを表示することを確認する。
    Args:
        monkeypatch: テスト中だけIP取得を差し替える仕組み。
    Returns:
        なし。
    """
    monkeypatch.setattr("kakeibo.__main__.local_ip_address", lambda: "192.168.1.23")

    assert display_url("0.0.0.0", 5050) == "http://192.168.1.23:5050/"


def test_display_url_keeps_explicit_host() -> None:
    """明示されたホストはそのまま表示することを確認する。
    Args:
        なし。
    Returns:
        なし。
    """
    assert display_url("localhost", 5050) == "http://localhost:5050/"


def test_local_ip_address_falls_back_to_loopback(monkeypatch) -> None:
    """IP取得に失敗したらローカルホストを返すことを確認する。
    Args:
        monkeypatch: テスト中だけsocketを差し替える仕組み。
    Returns:
        なし。
    """

    class FailingSocket:
        """接続失敗するsocketの代用品。
        Args:
            なし。
        Returns:
            なし。
        """

        def __enter__(self):
            """with文の開始処理。
            Args:
                なし。
            Returns:
                自分自身。
            """
            return self

        def __exit__(self, *args):
            """with文の終了処理。
            Args:
                args: 例外情報。
            Returns:
                なし。
            """
            return None

        def connect(self, address):
            """接続失敗を再現する。
            Args:
                address: 接続先。
            Returns:
                なし。
            """
            raise OSError("network unavailable")

    monkeypatch.setattr("kakeibo.__main__.socket.socket", lambda *args: FailingSocket())

    assert local_ip_address() == "127.0.0.1"
