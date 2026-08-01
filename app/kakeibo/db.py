"""PostgreSQLへの接続と基本操作をまとめる。"""

from contextlib import contextmanager
from typing import Iterator
from urllib.parse import urlsplit, urlunsplit

import psycopg
from psycopg import errors, sql
from psycopg.rows import dict_row

from .config import database_url as config_database_url


def database_url() -> str:
    """接続先URLを取得する。

    Args:
        なし。

    Returns:
        PostgreSQLの接続URL。
    """
    return config_database_url()


@contextmanager
def get_db() -> Iterator[psycopg.Connection]:
    """自動コミット・ロールバック付き接続を返す。

    Args:
        なし。

    Returns:
        接続を返すコンテキストマネージャー。
    """
    # DB停止時にもWeb画面が長く固まらないよう短時間で案内画面へ切り替える。
    with psycopg.connect(
        database_url(), row_factory=dict_row, connect_timeout=3
    ) as connection:
        with connection.transaction():
            yield connection


def maintenance_database_url() -> str:
    """DB作成用の接続URLを作る。

    Args:
        なし。

    Returns:
        DB名だけpostgresへ差し替えた接続URL。
    """
    parts = urlsplit(database_url())
    return urlunsplit((parts.scheme, parts.netloc, "/postgres", parts.query, parts.fragment))


def target_database_name() -> str:
    """接続URLから作成対象DB名を取り出す。

    Args:
        なし。

    Returns:
        作成対象のデータベース名。
    """
    parts = urlsplit(database_url())
    return parts.path.lstrip("/") or "kakeibo_dx"


def is_missing_database_error(exc: Exception) -> bool:
    """DB未作成エラーかどうかを判定する。
    Args:
        exc: PostgreSQL接続時に発生した例外。
    Returns:
        DBが存在しないエラーならTrue。
    """
    message = str(exc).lower()
    sqlstate = getattr(exc, "sqlstate", "")
    db_name = target_database_name().lower()
    return (
        isinstance(exc, errors.InvalidCatalogName)
        or sqlstate == "3D000"
        or "does not exist" in message
        or db_name in message and "password authentication failed" not in message
    )


def create_database_if_missing() -> None:
    """対象DBがなければ作成する。

    Args:
        なし。

    Returns:
        なし。
    """
    db_name = target_database_name()
    # DB名は識別子として安全に引用し、SQL注入を避ける。
    with psycopg.connect(maintenance_database_url(), autocommit=True, connect_timeout=3) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (db_name,),
        ).fetchone()
        if not exists:
            connection.execute(
                sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name))
            )


def init_schema() -> None:
    """必要なテーブルと索引を作成する。

    Args:
        なし。

    Returns:
        なし。
    """
    schema = """
    CREATE TABLE IF NOT EXISTS statement_imports (
        id BIGSERIAL PRIMARY KEY,
        file_name TEXT NOT NULL,
        file_hash CHAR(64) NOT NULL UNIQUE,
        statement_date DATE,
        imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        transaction_count INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS transactions (
        id BIGSERIAL PRIMARY KEY,
        import_id BIGINT REFERENCES statement_imports(id) ON DELETE SET NULL,
        used_at TIMESTAMP NOT NULL,
        time_known BOOLEAN NOT NULL DEFAULT FALSE,
        merchant TEXT NOT NULL,
        amount INTEGER NOT NULL CHECK (amount >= 0),
        category TEXT NOT NULL,
        payment_method TEXT,
        source_hash CHAR(64) NOT NULL UNIQUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_transactions_used_at ON transactions(used_at);
    CREATE INDEX IF NOT EXISTS idx_transactions_category ON transactions(category);
    CREATE TABLE IF NOT EXISTS category_rules (
        merchant_key TEXT PRIMARY KEY,
        category TEXT NOT NULL,
        sample_merchant TEXT NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """
    try:
        with get_db() as connection:
            connection.execute(schema)
    except Exception as exc:
        if not is_missing_database_error(exc):
            raise
        create_database_if_missing()
        with get_db() as connection:
            connection.execute(schema)


def check_connection() -> tuple[bool, str]:
    """DB接続状態を確認する。

    Args:
        なし。

    Returns:
        成否と画面表示用メッセージ。
    """
    try:
        with get_db() as connection:
            connection.execute("SELECT 1")
        return True, "PostgreSQL connected"
    except Exception as exc:
        return False, format_connection_error(exc)


def format_connection_error(exc: Exception) -> str:
    """接続エラーを画面向けの短い英語にする。

    Args:
        exc: PostgreSQL接続時に発生した例外。

    Returns:
        画面に表示する英語の接続エラーメッセージ。
    """
    message = str(exc).lower()
    sqlstate = getattr(exc, "sqlstate", "")
    if is_missing_database_error(exc):
        return (
            "PostgreSQL disconnected: database kakeibo_dx does not exist. "
            "Create it with pgAdmin or psql."
        )
    if (
        isinstance(exc, errors.InvalidPassword)
        or sqlstate == "28P01"
        or "password authentication failed" in message
    ):
        return (
            "PostgreSQL disconnected: authentication failed. "
            "Check the user and password in config/config.json."
        )
    if "connection timeout" in message or "connection refused" in message:
        return (
            "PostgreSQL disconnected: server is not running or the port is wrong. "
            "Check config/config.json and PostgreSQL service status."
        )
    return "PostgreSQL disconnected: check config/config.json and PostgreSQL service status."
