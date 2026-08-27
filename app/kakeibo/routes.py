"""Web画面とAPIのルートを定義する。"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

from .config import load_config, save_config
from .db import check_connection, database_url, format_connection_error, init_schema
from .parser import extract_pdf_text
from .services import (
    add_manual_transaction,
    dashboard_data,
    import_statement,
    normalize_period_value,
    period_navigation,
    remember_category_for_transaction,
    update_single_transaction_category,
)

bp = Blueprint("main", __name__)
CATEGORIES = ("食費", "日用品", "娯楽", "固定費", "交通", "医療・健康", "自己投資", "資産形成", "衣服・美容", "税金", "その他")
CATEGORY_COLORS = {
    "食費": "#65f5cf",
    "日用品": "#c3a07a",
    "娯楽": "#f6d77b",
    "固定費": "#35d6a9",
    "交通": "#75d7ff",
    "医療・健康": "#9bf28f",
    "自己投資": "#8fc7ff",
    "資産形成": "#b2f7d0",
    "衣服・美容": "#ff9fc7",
    "税金": "#d9a76b",
    "その他": "#a9b5ad",
}
CATEGORY_BACKGROUNDS = {
    "食費": "rgba(101,245,207,.12)",
    "日用品": "rgba(195,160,122,.13)",
    "娯楽": "rgba(246,215,123,.12)",
    "固定費": "rgba(53,214,169,.13)",
    "交通": "rgba(117,215,255,.12)",
    "医療・健康": "rgba(155,242,143,.12)",
    "自己投資": "rgba(143,199,255,.12)",
    "資産形成": "rgba(178,247,208,.12)",
    "衣服・美容": "rgba(255,159,199,.12)",
    "税金": "rgba(217,167,107,.13)",
    "その他": "rgba(169,181,173,.10)",
}
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
    sort_key = request.args.get("sort", "date")
    sort_dir = request.args.get("dir", "desc")
    if sort_key not in {"date", "merchant", "category", "amount"}:
        sort_key = "date"
    if sort_dir not in {"asc", "desc"}:
        sort_dir = "desc"
    grouped = request.args.get("grouped") == "1"
    active_category = request.args.get("category") or None
    if active_category not in CATEGORIES:
        active_category = None
    data = dashboard_data(period, selected, active_category, sort_key, sort_dir, grouped)
    return render_template(
        "dashboard.html",
        data=data,
        period=period,
        selected=normalize_period_value(period, selected),
        active_category=active_category or "",
        sort_key=sort_key,
        sort_dir=sort_dir,
        grouped=grouped,
        categories_json=json.dumps(data["categories"], ensure_ascii=False),
        monthly_json=json.dumps(data["monthly"], ensure_ascii=False),
        category_colors_json=json.dumps(CATEGORY_COLORS, ensure_ascii=False),
        categories=CATEGORIES,
        category_colors=CATEGORY_COLORS,
        category_backgrounds=CATEGORY_BACKGROUNDS,
        db_message=db_message,
        period_nav=period_navigation(period, selected),
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


@bp.post("/manual")
def add_manual():
    """手動入力された明細を保存する。

    Args:
        なし。

    Returns:
        入力日付の月表示へのリダイレクト。
    """
    used_on = request.form.get("used_on", "").strip()
    merchant = request.form.get("merchant", "").strip()
    amount_text = request.form.get("amount", "").replace(",", "").strip()
    category = request.form.get("category", "")
    payment_method = request.form.get("payment_method", "").strip() or "手動入力"
    if not used_on or not merchant or not amount_text:
        flash("日付、内容、金額を入力してください。", "error")
        return redirect(request.referrer or url_for("main.dashboard"))
    if category not in CATEGORIES:
        flash("カテゴリが正しくありません。", "error")
        return redirect(request.referrer or url_for("main.dashboard"))
    try:
        used_at = datetime.strptime(used_on, "%Y-%m-%d")
        amount = int(amount_text)
    except ValueError:
        flash("日付または金額の形式が正しくありません。", "error")
        return redirect(request.referrer or url_for("main.dashboard"))
    if amount <= 0:
        flash("金額は1円以上で入力してください。", "error")
        return redirect(request.referrer or url_for("main.dashboard"))
    add_manual_transaction(used_at, merchant, amount, category, payment_method)
    flash("手動明細を追加しました。", "success")
    return redirect(url_for("main.dashboard", period="month", value=used_on[:7]))


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
        apply_similar = request.form.get("apply_similar") == "1"
        if apply_similar:
            updated = remember_category_for_transaction(transaction_id, category)
            flash(f"カテゴリを更新しました。似た店舗名を含めて{updated}件に反映しました。", "success")
        else:
            update_single_transaction_category(transaction_id, category)
            flash("この明細だけカテゴリを更新しました。", "success")
    return redirect(request.referrer or url_for("main.dashboard"))
