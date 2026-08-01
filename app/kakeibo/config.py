"""JSON設定の読み書きをまとめる。"""

import json
import secrets
from pathlib import Path
from urllib.parse import quote


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config" / "config.json"


def default_config() -> dict:
    """既定の設定を作る。

    Args:
        なし。

    Returns:
        アプリ全体の既定設定。
    """
    return {
        "database": {
            "user": "postgres",
            "password": "postgres",
            "host": "localhost",
            "port": 5432,
            "name": "kakeibo_dx",
        },
        "server": {
            "host": "127.0.0.1",
            "port": None,
            "debug": True,
            "open_browser": True,
        },
        "security": {
            "secret_key": secrets.token_urlsafe(32),
        },
    }


def deep_merge(base: dict, override: dict) -> dict:
    """既定設定へ保存済み設定を重ねる。

    Args:
        base: 土台になる設定。
        override: 上書きする設定。

    Returns:
        マージ済み設定。
    """
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config() -> dict:
    """JSON設定を読み込む。

    Args:
        なし。

    Returns:
        アプリ設定。
    """
    config = default_config()
    if CONFIG_PATH.exists():
        saved = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
        config = deep_merge(config, saved)
    return config


def save_config(config: dict) -> None:
    """JSON設定を保存する。

    Args:
        config: 保存するアプリ設定。

    Returns:
        なし。
    """
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def database_url(config: dict | None = None) -> str:
    """DB接続URLをJSON設定から作る。

    Args:
        config: アプリ設定。省略時はファイルから読む。

    Returns:
        PostgreSQL接続URL。
    """
    current = config or load_config()
    database = current["database"]
    user = quote(str(database["user"]), safe="")
    password = quote(str(database["password"]), safe="")
    host = database["host"]
    port = int(database["port"])
    name = database["name"]
    return f"postgresql://{user}:{password}@{host}:{port}/{name}"
