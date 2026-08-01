"""Web画面とAPIのルートを定義する。"""

import json
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

from .config import load_config, save_config
from .db import check_connection, database_url, format_connection_error, get_db, init_schema
from .parser import extract_pdf_text
from .services import dashboard_data, import_statement

bp = Blueprint("main", __name__)
CATEGORIES = ("食費", "日用品", "娯楽", "固定費", "交通", "医療・健康", "自己投資", "資産形成", "衣服・美容", "その他")
FAILED_UPLOAD_FOLDER = "failed_uploads"


def current_database_settings() -> dict[str, str]:
    """接続フォームの初期値を作る。
    Args:
        なし。
    Returns:
        画面に表示してよいDB接続設定。
    """
    parts = urlsplit(database_url())
    return {
        "user": parts.username or "postgres",
        "host": parts.hostname or "localhost",
        "port": str(parts.port or 5432),
        "database": parts.path.lstrip("/") or "kakeibo_dx",
    }


def save_database_config(user: str, password: str, host: str, port: str, database: str) -> None:
    """DB接続情報をJSON設定へ保存する。
    Args:
        user: PostgreSQLのユーザー名。
        password: PostgreSQLのパスワード。
        host: PostgreSQLサーバー名。
        port: PostgreSQLのポート番号。
        database: 接続先データベース名。
    Returns:
        なし。
    """
    config = load_config()
    config["database"] = {
        "user": user,
        "password": password,
        "host": host,
        "port": int(port),
        "name": database,
    }
    save_config(config)


def move_to_failed_uploads(path: Path) -> Path:
    """取込失敗PDFを調査用フォルダへ移す。
    Args:
        path: 取込に失敗したPDFの保存先。
    Returns:
        移動後のPDFパス。
    """
    failed_dir = path.parent.parent / FAILED_UPLOAD_FOLDER
    failed_dir.mkdir(parents=True, exist_ok=True)
    failed_path = failed_dir / path.name
    path.replace(failed_path)
    return failed_path


def write_failed_upload_text_report(pdf_path: Path, exc: Exception) -> Path:
    """取込失敗PDFの抽出テキストを保存する。
    Args:
        pdf_path: 調査用フォルダへ移したPDF。
        exc: 取込時の例外。
    Returns:
        保存したテキストファイルのパス。
    """
    report_path = pdf_path.with_suffix(".txt")
    try:
        text = extract_pdf_text(pdf_path)
    except Exception as text_exc:
        text = f"PDFテキスト抽出にも失敗しました: {text_exc}"
    report = (
        f"file: {pdf_path.name}\n"
        f"error: {exc}\n"
        "\n"
        "---- extracted text ----\n"
        f"{text}\n"
    )
    report_path.write_text(report, encoding="utf-8")
    return report_path


@bp.get("/")
def dashboard():
    """ダッシュボードを表示する。

    Args:
        なし。

    Returns:
        HTMLレスポンス。
    """
    connected, db_message = check_connection()
    if not connected:
        return render_template(
            "setup.html",
            db_message=db_message,
            db_settings=current_database_settings(),
        )
    period = request.args.get("period", "month")
    selected = request.args.get("value")
    data = dashboard_data(period, selected)
    return render_template(
        "dashboard.html",
        data=data,
        period=period,
        selected=selected or "",
        categories_json=json.dumps(data["categories"], ensure_ascii=False),
        monthly_json=json.dumps(data["monthly"], ensure_ascii=False),
        categories=CATEGORIES,
        db_message=db_message,
    )


@bp.post("/setup")
def setup_database():
    """DBテーブル作成を再試行する。

    Args:
        なし。

    Returns:
        ダッシュボードへのリダイレクト。
    """
    try:
        init_schema()
        flash("PostgreSQLの準備が完了しました。", "success")
    except Exception as exc:
        flash(format_connection_error(exc), "error")
    return redirect(url_for("main.dashboard"))


@bp.post("/setup/database-config")
def update_database_config():
    """画面からDB接続情報を更新する。
    Args:
        なし。
    Returns:
        ダッシュボードへのリダイレクト。
    """
    user = request.form.get("user", "").strip()
    password = request.form.get("password", "")
    host = request.form.get("host", "").strip() or "localhost"
    port = request.form.get("port", "").strip() or "5432"
    database = request.form.get("database", "").strip() or "kakeibo_dx"
    if not user or not password:
        flash("PostgreSQLのユーザー名とパスワードを入力してください。", "error")
        return redirect(url_for("main.dashboard"))
    if not port.isdigit():
        flash("PostgreSQLのポート番号は数字で入力してください。", "error")
        return redirect(url_for("main.dashboard"))
    save_database_config(user, password, host, port, database)
    try:
        init_schema()
        flash("PostgreSQLの接続情報を保存し、準備が完了しました。", "success")
    except Exception as exc:
        flash(format_connection_error(exc), "error")
    return redirect(url_for("main.dashboard"))


@bp.post("/import")
def import_pdf():
    """アップロードPDFをまとめて取り込む。

    Args:
        なし。

    Returns:
        ダッシュボードへのリダイレクト。
    """
    uploads = [
        file
        for field_name in ("statements", "statement")
        for file in request.files.getlist(field_name)
        if file.filename
    ]
    if not uploads:
        flash("PDFファイルを選択してください。", "error")
        return redirect(url_for("main.dashboard"))
    total_extracted = 0
    total_saved = 0
    success_files = 0
    duplicate_files = 0
    failed_messages = []
    for uploaded in uploads:
        if Path(uploaded.filename).suffix.lower() != ".pdf":
            failed_messages.append(f"{uploaded.filename}: PDFファイルではありません。")
            continue
        safe_name = secure_filename(uploaded.filename) or "statement.pdf"
        destination = Path(current_app.config["UPLOAD_FOLDER"]) / f"{uuid.uuid4().hex}_{safe_name}"
        uploaded.save(destination)
        try:
            extracted, saved = import_statement(destination, uploaded.filename)
            total_extracted += extracted
            total_saved += saved
            success_files += 1
            if saved == 0:
                duplicate_files += 1
        except Exception as exc:
            failed_path = move_to_failed_uploads(destination)
            report_path = write_failed_upload_text_report(failed_path, exc)
            failed_messages.append(
                f"{uploaded.filename}: {exc} 保存先: {failed_path} / {report_path}"
            )
    if total_extracted:
        message = f"{len(uploads)}ファイル中{success_files}ファイルを取り込み、{total_extracted}件を解析し、{total_saved}件を保存しました。"
        if duplicate_files:
            message += f" {duplicate_files}ファイルは登録済みでした。"
        flash(message, "success")
    for failed_message in failed_messages:
        flash(f"取込に失敗しました: {failed_message}", "error")
    return redirect(url_for("main.dashboard", period="all"))


@bp.post("/transactions/<int:transaction_id>/category")
def update_category(transaction_id: int):
    """明細カテゴリを手動修正する。

    Args:
        transaction_id: 修正する明細ID。

    Returns:
        元画面へのリダイレクト。
    """
    category = request.form.get("category", "")
    if category not in CATEGORIES:
        flash("カテゴリが正しくありません。", "error")
    else:
        with get_db() as connection:
            connection.execute(
                "UPDATE transactions SET category = %s WHERE id = %s",
                (category, transaction_id),
            )
        flash("カテゴリを更新しました。", "success")
    return redirect(request.referrer or url_for("main.dashboard"))
