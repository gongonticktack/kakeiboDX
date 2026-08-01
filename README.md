# Kakeibo DX

クレジットカードの利用明細PDFを取り込み、PostgreSQLへ保存して支出を見える化するローカルWeb家計簿です。Python / Flask を主体にしており、グラフも外部CDNへ接続せずブラウザ内で描画します。

## 主な機能

- 楽天カード請求明細PDFから利用日、利用会社、金額、支払方法を自動抽出
- 店舗名からカテゴリを自動推定し、画面上で修正
- PDFと明細のハッシュによる重複登録防止
- 月、年、累計のカテゴリ別円グラフ
- 月ごとの支出棒グラフ
- 支出割合に応じた節約アドバイス
- PostgreSQLへの永続保存

カード明細に利用時刻が記載されていない場合、DBの `used_at` は当日の `00:00:00`、`time_known` は `false` になります。画面では誤解を避けるため日付だけ表示します。

## セットアップ

PowerShellでプロジェクト直下から実行します。

```powershell
C:\Users\gtakk\AppData\Local\Programs\Python\Python313\python.exe -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

PostgreSQLが入っていない場合、`start.bat` の起動時にインストールするかどうかを確認します。インストールを選ぶと `winget` で PostgreSQL を入れます。インストール先は、空のまま Enter を押すと既定の場所、任意のフォルダを入力するとその場所を指定します。既存の `C:\Program Files\PostgreSQL\...` も検出します。

すでに別の場所へインストール済みなのに検出されない場合は、`Existing PostgreSQL folder:` と表示されたところで、例のようにPostgreSQLのインストール先を入力してください。

```text
C:\path\to\PostgreSQL
```

`winget` が使えない環境では、PostgreSQLを手動でインストールしてから `start.bat` をもう一度実行してください。

PostgreSQLへ接続できる状態なら、起動時にデータベースとテーブルを自動作成します。手動で作る場合は、PostgreSQL側で次のSQLを実行してください。

```sql
CREATE DATABASE kakeibo_dx;
```

接続情報と起動設定は `config/config.json` に保存します。手動で変更する場合は、実際のPostgreSQLユーザー名とパスワードに合わせてください。
`config/config.json` が無いPCでは、`start.bat` の起動時に会話形式でPostgreSQL接続情報とWebサーバー設定を確認し、このJSONを自動作成します。パスワードは入力中に表示されません。

```json
{
  "database": {
    "user": "postgres",
    "password": "実際のパスワード",
    "host": "localhost",
    "port": 5432,
    "name": "kakeibo_dx"
  },
  "server": {
    "host": "127.0.0.1",
    "port": null,
    "debug": true,
    "open_browser": true
  },
  "security": {
    "secret_key": "十分に長い任意の文字列"
  }
}
```

PostgreSQLのポートを `5432` 以外にしている場合は、`database.port` も実際の値に合わせてください。
`server.port` が `null` または `0` の場合は、起動時に他サービスと被らない空きポートを自動選択します。固定したい場合だけ任意のポート番号を入れてください。

画面に `PostgreSQL disconnected: authentication failed.` と表示された場合は、`config/config.json` のユーザー名またはパスワードがPostgreSQL側と一致していません。起動したブラウザのDBセットアップ画面で、実際のPostgreSQLユーザー名、パスワード、ホスト、ポート、データベース名を入力して `接続情報を保存` を押してください。保存後、`config/config.json` が更新され、接続確認とテーブル作成が再実行されます。

## 起動

`start.bat` をダブルクリックするか、PowerShellで実行します。

```powershell
.\start.bat
```

`start.bat` から起動すると、コンソールに `http://自身のIP:ポート番号/` が表示されます。対応しているターミナルでは、そのURLをクリックして画面を開けます。既定ブラウザの自動起動も行います。ポートは起動時に空いている番号を自動選択します。画面上部の取込欄からPDFを選んでください。複数のPDFをまとめて選択できます。初回接続時にテーブルと索引は自動作成されます。

同じPDFを再度取り込んだ場合は、PDFのハッシュと明細ごとのハッシュで重複登録を防ぎます。複数PDFのうち一部だけ失敗した場合も、取り込めたPDFは保存され、失敗したファイル名が画面に表示されます。
解析に失敗したPDFは調査用に `storage/failed_uploads/` へ保存されます。同じ場所にPDFから抽出したテキストの `.txt` も保存します。楽天カードのPDF形式が変わって読み取れない場合は、このフォルダのPDFとテキストを確認してパーサーを調整します。

起動に失敗した場合、`start.bat` はエラーコードを表示した状態でコンソールを残します。画面上のエラーと `logs/` 内の最新アプリログを確認してください。

## テストと確認

```powershell
$env:PYTHONPATH="$PWD\app"
.\.venv\Scripts\python.exe -m compileall app
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m flask --app kakeibo routes
```

実際のPDFをDBへ保存せず解析件数だけ確認する例:

```powershell
$env:PYTHONPATH="$PWD\app"
.\.venv\Scripts\python.exe -c "from kakeibo.parser import parse_pdf; rows, issued = parse_pdf(r'C:\Users\gtakk\Downloads\statement_202607.pdf'); print(issued, len(rows), sum(x.amount for x in rows))"
```

## データと運用

- アップロード済みPDF: `storage/uploads/`
- 解析に失敗したPDF: `storage/failed_uploads/`
- 一時的なPDF確認物: `tmp/pdfs/`
- 接続情報と起動設定: `config/config.json`（Git管理対象外）
- アプリログ: `logs/app_YYYYMMDD_HHMMSS_ffffff.log`
- HTTPアクセスログ: `logs/access_YYYYMMDD_HHMMSS_ffffff.log`
- PDFはローカルPC内だけで処理され、外部AIや外部APIへ送信しません。
- 現在のパーサーは楽天カードの請求明細レイアウト向けです。他社カードは表形式が異なるため、専用パーサーの追加が必要です。

ログは起動ごとに新しいファイルを作成します。アプリログとアクセスログは種類ごとに直近5件だけ残し、それより古いファイルは次回起動時に自動削除します。
