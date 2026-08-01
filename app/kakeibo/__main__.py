"""ローカル開発サーバーを起動する。"""

import os
import socket
import threading
import webbrowser

from . import create_app
from .config import ensure_fixed_server_port, load_config, save_config


def open_browser_later(url: str, delay_seconds: float = 1.0) -> None:
    """サーバー起動直後に既定ブラウザを開く。

    Args:
        url: ブラウザで開くローカルURL。
        delay_seconds: サーバーの待受開始を待つ秒数。

    Returns:
        なし。
    """
    timer = threading.Timer(delay_seconds, webbrowser.open, args=(url,))
    timer.daemon = True
    timer.start()


def env_bool(name: str, default: bool) -> bool:
    """環境変数の真偽値を読む。

    Args:
        name: 環境変数名。
        default: 未指定時の値。

    Returns:
        真偽値。
    """
    value = os.getenv(name)
    if value is None:
        return default
    return value == "1"


def choose_port(configured_port: int | None) -> int:
    """起動に使う固定ポート番号を決める。

    Args:
        configured_port: JSON設定のポート番号。

    Returns:
        Webサーバーで使うポート番号。
    """
    if configured_port:
        return int(configured_port)
    raise ValueError("server.port is not configured.")


def local_ip_address() -> str:
    """このPCのLAN向けIPアドレスを取得する。

    Args:
        なし。

    Returns:
        取得できたIPアドレス。失敗時は127.0.0.1。
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return str(sock.getsockname()[0])
    except OSError:
        return "127.0.0.1"


def display_url(host: str, port: int) -> str:
    """コンソールに表示するURLを作る。

    Args:
        host: サーバーの待受ホスト。
        port: サーバーの待受ポート。

    Returns:
        ブラウザで開けるURL。
    """
    display_host = local_ip_address() if host in {"0.0.0.0", "::"} else host
    return f"http://{display_host}:{port}/"


def main() -> None:
    """JSON設定に従ってWebサーバーを起動する。

    Args:
        なし。

    Returns:
        なし。
    """
    config = load_config()
    config, changed = ensure_fixed_server_port(config)
    if changed:
        save_config(config)
    server = config["server"]
    app = create_app()
    host = server["host"]
    port = choose_port(server.get("port"))
    debug = bool(server["debug"])
    url = display_url(host, port)
    should_open_browser = env_bool("OPEN_BROWSER", bool(server["open_browser"]))
    is_serving_process = not debug or os.getenv("WERKZEUG_RUN_MAIN") == "true"
    if is_serving_process:
        print(f"Kakeibo DX: {url}", flush=True)
    # デバッグ再起動時にブラウザが2枚開くのを防ぐ。
    if should_open_browser and is_serving_process:
        open_browser_later(url)
    app.run(
        host=host,
        port=port,
        debug=debug,
    )


if __name__ == "__main__":
    main()
