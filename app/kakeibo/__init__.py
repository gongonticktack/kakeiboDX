"""家計簿Webアプリの初期化を行う。"""

from pathlib import Path

from flask import Flask

from .config import load_config
from .db import init_schema
from .logging_config import configure_logging
from .routes import bp


def create_app(test_config: dict | None = None) -> Flask:
    """Flaskアプリを作成する。

    Args:
        test_config: テスト時に上書きする設定。

    Returns:
        設定済みのFlaskアプリ。
    """
    project_root = Path(__file__).resolve().parents[2]
    config = load_config()
    if not test_config or not test_config.get("TESTING"):
        configure_logging(project_root)
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_mapping(
        SECRET_KEY=config["security"]["secret_key"],
        MAX_CONTENT_LENGTH=16 * 1024 * 1024,
        UPLOAD_FOLDER=project_root / "storage" / "uploads",
    )
    if test_config:
        app.config.update(test_config)
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    app.register_blueprint(bp)

    if not app.config.get("TESTING"):
        try:
            init_schema()
        except Exception as exc:  # 起動後の画面で設定方法を案内するため止めない。
            app.logger.warning("PostgreSQL initialization was deferred: %s", exc)
    return app
