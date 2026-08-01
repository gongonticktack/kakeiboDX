"""JSON設定のテスト。"""

from pathlib import Path

from kakeibo import config


def test_load_config_merges_saved_json(monkeypatch, tmp_path: Path) -> None:
    """保存済みJSONを既定値に重ねて読めることを確認する。
    Args:
        monkeypatch: テスト中だけ設定パスを差し替える仕組み。
        tmp_path: 一時保存先。
    Returns:
        なし。
    """
    config_path = tmp_path / "config.json"
    config_path.write_text(
        '{"database":{"password":"secret"},"server":{"port":5050}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "CONFIG_PATH", config_path)

    loaded = config.load_config()

    assert loaded["database"]["user"] == "postgres"
    assert loaded["database"]["password"] == "secret"
    assert loaded["server"]["port"] == 5050


def test_database_url_encodes_json_config(monkeypatch, tmp_path: Path) -> None:
    """JSON設定から接続URLを作れることを確認する。
    Args:
        monkeypatch: テスト中だけ設定パスを差し替える仕組み。
        tmp_path: 一時保存先。
    Returns:
        なし。
    """
    config_path = tmp_path / "config.json"
    config_path.write_text(
        """
        {
          "database": {
            "user": "postgres",
            "password": "p@ss/word",
            "host": "127.0.0.1",
            "port": 5433,
            "name": "kakeibo_dx"
          }
        }
        """,
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "CONFIG_PATH", config_path)

    assert (
        config.database_url()
        == "postgresql://postgres:p%40ss%2Fword@127.0.0.1:5433/kakeibo_dx"
    )


def test_ensure_fixed_server_port_sets_random_once(monkeypatch) -> None:
    """未設定ポートへ固定ランダム値を入れることを確認する。
    Args:
        monkeypatch: テスト中だけランダム値を差し替える仕組み。
    Returns:
        なし。
    """
    monkeypatch.setattr(config, "random_application_port", lambda: 61234)

    updated, changed = config.ensure_fixed_server_port({"server": {"port": None}})

    assert changed is True
    assert updated["server"]["port"] == 61234


def test_ensure_fixed_server_port_keeps_existing_port() -> None:
    """既存ポートは変更しないことを確認する。
    Args:
        なし。
    Returns:
        なし。
    """
    updated, changed = config.ensure_fixed_server_port({"server": {"port": 61234}})

    assert changed is False
    assert updated["server"]["port"] == 61234
