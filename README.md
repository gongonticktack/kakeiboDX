💻 **ローカルWebアプリの接続先：起動時にコンソールへ表示されるURL** — `start.bat`で起動したPC内で利用できます。ポートは`config/config.json`の`server.port`に保存されるため、固定URLではありません。

# Kakeibo DX

## 概要

クレジットカードの利用明細PDFを取り込み、支出をPostgreSQLへ保存して、月別・年別・カテゴリ別に確認するローカルWeb家計簿です。Flaskの画面で明細とグラフを閲覧できます。

## 主な機能

- PDF明細の読み取りと支出データの登録。
- 月別・年別の支出集計とグラフ。
- 明細一覧とカテゴリ別の傾向確認。
- 初回のDB接続設定ウィザード。

## 推奨要件

| 項目 | 環境 |
| --- | --- |
| OS | Windows（`start.bat`の起動対象） |
| Python | 3.11を推奨 |
| DB | PostgreSQL Serverと`psql` |
| ブラウザ | 現行のChromeまたはEdge |
| 入力 | 対応書式のクレジットカード明細PDF |

画像だけのPDFは通常のテキスト抽出では解析できません。PDFの書式によって取り込み結果が異なります。

## 必要なライブラリ

`requirements.txt`で固定しています。

| ライブラリ | バージョン | 用途 |
| --- | --- | --- |
| Flask | 3.1.1 | Web画面・API |
| pdfplumber | 0.11.7 | PDFテキスト抽出 |
| psycopg[binary] | 3.2.9 | PostgreSQL接続 |

## 使い方

### 初回セットアップ

現在の`start.bat`は仮想環境の作成・Python依存関係の導入を行わないため、先にルートで次を実行します。

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

1. PostgreSQLをインストールし、サービスを起動します。
2. `start.bat`をダブルクリックします。PostgreSQLが見つからない場合は既存のインストール先指定、またはwingetによる導入案内が表示されます。
3. 初回ウィザードでDBユーザー、パスワード、接続先、DB名を入力します。
4. 設定が`config/config.json`へ保存されます。
5. コンソールに表示されたURL、または自動で開くブラウザから操作します。

ポートは高番台から選んだ値を設定に保存して使用します。固定の5000番ポートではありません。

### 日常の操作

PDF明細をアップロードし、取り込み結果を確認します。ダッシュボードの期間・カテゴリを切り替えて支出を確認します。終了するときは起動したコンソールで`Ctrl+C`を押します。

### 手動起動

```powershell
$env:PYTHONPATH = "$PWD\app"
.\.venv\Scripts\python.exe -m kakeibo
```

## 設定と保存先

| 項目 | 内容 |
| --- | --- |
| `config/config.json` | DB接続、サーバー設定、セッション用キー |
| `database` | PostgreSQLユーザー・パスワード・ホスト・ポート・DB名 |
| `server` | 待受ホスト・ポート・デバッグ・ブラウザ自動起動 |
| `storage/uploads/` | アップロード明細 |
| `logs/` | コンソール・アプリログ。種類ごとに直近5件 |

既定の待受ホストは`0.0.0.0`、デバッグは有効です。自分のPC内だけで使う場合は`server.host`を`127.0.0.1`に設定できます。明細・DBパスワード・設定ファイルは公開リポジトリへ登録しないでください。

## フォルダ構成

| 相対パス | 役割 |
| --- | --- |
| `app/kakeibo/` | 起動、設定、PDF解析、DB、集計処理 |
| `app/kakeibo/templates/` | HTML画面 |
| `app/kakeibo/static/` | CSSとグラフ表示JavaScript |
| `tests/` | 設定・解析・集計・ルートのテスト |
| `storage/uploads/` | 入力ファイル |
| `logs/` | ログ |
| `config/` | 初回設定時に生成 |
| `requirements.txt` | Python依存関係 |
| `start.bat` | Windows起動入口 |

## 仕組み

PDFから文字を取り出し、日付・利用先・金額などを明細として整理します。PostgreSQLに登録した明細を集計し、ブラウザにグラフと一覧を表示します。

## 確認方法

テスト用にpytestを追加導入します（実行用requirements.txtには含まれていません）。

```powershell
$env:PYTHONPATH = "$PWD\app"
.\.venv\Scripts\python.exe -m pip install pytest
.\.venv\Scripts\python.exe -m pytest
```

## トラブル対処

- 仮想環境がない：初回セットアップの2コマンドを実行してください。
- DB接続失敗：PostgreSQLサービス、接続情報、権限を確認してください。
- 起動ポートが使用中：`config/config.json`の`server.port`を変更してください。
- PDFの解析失敗：最新ログとPDF書式、抽出可能な文字があるかを確認してください。
