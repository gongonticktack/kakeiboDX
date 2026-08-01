"""ログ保存と世代管理のテスト。"""

import logging
from pathlib import Path

from kakeibo.logging_config import _keep_latest, configure_logging


def test_logging_creates_both_log_types(tmp_path: Path) -> None:
    """アプリ用とアクセス用のログを作成することを確認する。"""
    app_log, access_log = configure_logging(tmp_path)
    assert app_log.exists()
    assert access_log.exists()
    logging.getLogger().handlers.clear()
    logging.getLogger("werkzeug").handlers.clear()


def test_keep_latest_five_files(tmp_path: Path) -> None:
    """種類ごとに新しいログ5件だけ残すことを確認する。"""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    for index in range(7):
        path = log_dir / f"app_{index}.log"
        path.write_text(str(index), encoding="utf-8")
        path.touch()
    _keep_latest(log_dir, "app_*.log", 5)
    assert len(list(log_dir.glob("app_*.log"))) == 5
