"""アプリログとアクセスログの保存設定を行う。"""

import logging
from datetime import datetime
from pathlib import Path


def configure_logging(project_root: Path) -> tuple[Path, Path]:
    """起動ごとのログファイルを作り、古いログを整理する。

    Args:
        project_root: プロジェクト直下のパス。

    Returns:
        アプリログとアクセスログの保存先。
    """
    log_dir = project_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    app_log = log_dir / f"app_{timestamp}.log"
    access_log = log_dir / f"access_{timestamp}.log"

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    app_handler = logging.FileHandler(app_log, encoding="utf-8")
    app_handler.setFormatter(formatter)
    access_handler = logging.FileHandler(access_log, encoding="utf-8")
    access_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(app_handler)

    # HTTPアクセスは専用ファイルへ分けると問題を探しやすい。
    werkzeug_logger = logging.getLogger("werkzeug")
    werkzeug_logger.setLevel(logging.INFO)
    werkzeug_logger.propagate = False
    werkzeug_logger.addHandler(access_handler)

    _keep_latest(log_dir, "app_*.log", 5)
    _keep_latest(log_dir, "access_*.log", 5)
    return app_log, access_log


def _keep_latest(log_dir: Path, pattern: str, keep: int) -> None:
    """指定種類のログを新しい順に残す。

    Args:
        log_dir: ログフォルダ。
        pattern: 対象ファイルの検索パターン。
        keep: 残すファイル数。

    Returns:
        なし。
    """
    files = sorted(log_dir.glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True)
    for old_file in files[keep:]:
        old_file.unlink(missing_ok=True)

