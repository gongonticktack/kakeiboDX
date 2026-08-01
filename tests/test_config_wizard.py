"""初回設定ウィザードのテスト。"""

from kakeibo.config_wizard import build_config


def test_build_config_uses_answers() -> None:
    """質問の回答がJSON設定へ入ることを確認する。

    Args:
        なし。

    Returns:
        なし。
    """
    answers = iter(
        [
            "admin",
            "db.example.local",
            "5433",
            "household",
            "0.0.0.0",
            "5050",
            "n",
            "y",
        ]
    )

    config = build_config(
        input_func=lambda prompt: next(answers),
        password_func=lambda prompt: "secret",
    )

    assert config["database"] == {
        "user": "admin",
        "password": "secret",
        "host": "db.example.local",
        "port": 5433,
        "name": "household",
    }
    assert config["server"] == {
        "host": "0.0.0.0",
        "port": 5050,
        "debug": False,
        "open_browser": True,
    }


def test_build_config_uses_defaults() -> None:
    """空入力なら標準設定を使うことを確認する。

    Args:
        なし。

    Returns:
        なし。
    """
    answers = iter(["", "", "", "", "", "", "", ""])

    config = build_config(
        input_func=lambda prompt: next(answers),
        password_func=lambda prompt: "",
    )

    assert config["database"]["user"] == "postgres"
    assert config["database"]["password"] == "postgres"
    assert config["database"]["host"] == "localhost"
    assert config["database"]["port"] == 5432
    assert config["database"]["name"] == "kakeibo_dx"
    assert config["server"]["host"] == "127.0.0.1"
    assert config["server"]["port"] is None
    assert config["server"]["debug"] is True
    assert config["server"]["open_browser"] is True
