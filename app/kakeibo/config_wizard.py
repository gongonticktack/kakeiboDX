"""初回起動用の対話式設定を行う。"""

import getpass
from typing import Callable

from .config import default_config, random_application_port, save_config


def ask_text(
    prompt: str,
    default: str,
    input_func: Callable[[str], str] = input,
) -> str:
    """文字列の設定値を質問する。

    Args:
        prompt: 画面に表示する質問文。
        default: 空入力時に使う値。
        input_func: 入力を受け取る関数。

    Returns:
        入力された文字列。
    """
    answer = input_func(f"{prompt} [{default}]: ").strip()
    return answer or default


def ask_int(
    prompt: str,
    default: int,
    input_func: Callable[[str], str] = input,
) -> int:
    """整数の設定値を質問する。

    Args:
        prompt: 画面に表示する質問文。
        default: 空入力時に使う値。
        input_func: 入力を受け取る関数。

    Returns:
        入力された整数。
    """
    while True:
        answer = input_func(f"{prompt} [{default}]: ").strip()
        if not answer:
            return default
        if answer.isdigit():
            return int(answer)
        print("Please enter a number.")


def ask_bool(
    prompt: str,
    default: bool,
    input_func: Callable[[str], str] = input,
) -> bool:
    """真偽値の設定を質問する。

    Args:
        prompt: 画面に表示する質問文。
        default: 空入力時に使う値。
        input_func: 入力を受け取る関数。

    Returns:
        入力された真偽値。
    """
    default_label = "Y" if default else "N"
    while True:
        answer = input_func(f"{prompt} [Y/N, default {default_label}]: ").strip().lower()
        if not answer:
            return default
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        print("Please enter Y or N.")


def build_config(
    input_func: Callable[[str], str] = input,
    password_func: Callable[[str], str] = getpass.getpass,
) -> dict:
    """質問の回答からJSON設定を作る。

    Args:
        input_func: 入力を受け取る関数。
        password_func: パスワード入力を受け取る関数。

    Returns:
        アプリ設定。
    """
    config = default_config()
    print("")
    print("First setup: create config/config.json for Kakeibo DX")
    print("")
    print("PostgreSQL settings")
    db_user = ask_text("PostgreSQL user", "postgres", input_func)
    db_password = password_func("PostgreSQL password: ")
    if not db_password:
        db_password = "postgres"
    db_host = ask_text("PostgreSQL host", "localhost", input_func)
    db_port = ask_int("PostgreSQL port", 5432, input_func)
    db_name = ask_text("Database name", "kakeibo_dx", input_func)

    print("")
    print("Web server settings")
    server_host = ask_text("Server host", "0.0.0.0", input_func)
    server_port = ask_int("Server port", random_application_port(), input_func)
    debug = ask_bool("Debug mode", True, input_func)
    open_browser = ask_bool("Open browser automatically", True, input_func)

    config["database"] = {
        "user": db_user,
        "password": db_password,
        "host": db_host,
        "port": db_port,
        "name": db_name,
    }
    config["server"] = {
        "host": server_host,
        "port": server_port,
        "debug": debug,
        "open_browser": open_browser,
    }
    return config


def main() -> None:
    """対話式に設定ファイルを作成する。

    Args:
        なし。

    Returns:
        なし。
    """
    config = build_config()
    save_config(config)
    print("")
    print("config/config.json was created.")


if __name__ == "__main__":
    main()
