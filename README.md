# Kakeibo DX

クレジットカードの利用明細PDFを取り込み、PostgreSQLへ保存して支出を見える化するローカルWeb家計簿です。Python / Flask を主体にしており、グラフも外部CDNへ接続せずブラウザ内で描画します。

## 主な機能

- 楽天カード請求明細PDFから利用日、利用会社、金額、支払方法を自動抽出
- 現金払いなどを画面から手動入力
- 店舗名からカテゴリを自動推定し、画面上で修正
- カテゴリ推定は、PDFに出てきた店舗だけでなく、主要な通販・スーパー・通信・交通・医療・学習・投資・娯楽・税金・保険サービス名にも対応
- PDFと明細のハッシュによる重複登録防止
- 月、年、累計のカテゴリ別円グラフ
- 月、年表示の前後移動
- 月ごとの支出棒グラフ
- 円グラフや棒グラフのクリックによる明細絞り込み
- 明細行のカテゴリ別背景色表示
- 明細一覧の全件表示と項目名クリックによる並び替え
- チョコミント配色のブラックモードUI
- 手動カテゴリ変更の学習と似た店舗名への自動反映
- 支出割合とカテゴリ傾向に応じた節約アドバイス
- 一人暮らし平均と比べたカテゴリ別差額グラフ
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
    "host": "0.0.0.0",
    "port": 64159,
    "debug": true,
    "open_browser": true
  },
  "security": {
    "secret_key": "十分に長い任意の文字列"
  }
}
```

PostgreSQLのポートを `5432` 以外にしている場合は、`database.port` も実際の値に合わせてください。
`server.port` は有名な利用ポートを避けた高番台ポートを1つ固定で使います。`config/config.json` が無い初回セットアップではランダムな高番台ポートを提案し、空入力ならその値を保存します。別の番号に固定したい場合だけ任意のポート番号を入れてください。`server.host` は、コンソールに表示される `http://自身のIP:ポート番号/` で開けるよう、通常は `0.0.0.0` にします。

画面に `PostgreSQL disconnected: authentication failed.` と表示された場合は、`config/config.json` のユーザー名またはパスワードがPostgreSQL側と一致していません。起動したブラウザのDBセットアップ画面で、実際のPostgreSQLユーザー名、パスワード、ホスト、ポート、データベース名を入力して `接続情報を保存` を押してください。保存後、`config/config.json` が更新され、接続確認とテーブル作成が再実行されます。

## 起動

`start.bat` をダブルクリックするか、PowerShellで実行します。

```powershell
.\start.bat
```

`start.bat` から起動すると、コンソールに `http://自身のIP:ポート番号/` が表示されます。対応しているターミナルでは、そのURLをクリックして画面を開けます。既定ブラウザの自動起動も行います。ポートは `config/config.json` に保存された固定ポートを使います。画面上部の取込欄からPDFを選んでください。複数のPDFをまとめて選択できます。初回接続時にテーブルと索引は自動作成されます。

月表示または年表示では、期間フォーム左右の矢印から前月・翌月、前年・翌年へ移動できます。URLの期間値が壊れている場合は、月表示なら今月、年表示なら今年へ戻して表示します。追加カードではカード明細PDFの取込と手入力の2種類を選べます。`手入力で追加` ボタンを押すとポップアップが開き、日付、内容、金額、カテゴリ、支払方法を入れて明細を追加できます。円グラフをクリックすると下の明細をそのカテゴリで絞り込み、棒グラフをクリックするとその月へ移動します。明細一覧は選択中の期間内の全件を表示し、利用日、利用会社、カテゴリ、金額の項目名をクリックすると昇順・降順を切り替えられます。明細のカテゴリを手動変更すると、その店舗名を正規化したルールを保存し、似た店舗名の既存明細と今後取り込む明細へ同じカテゴリを反映します。税金カテゴリは地方税共同機構(eLTAX)、国税、住民税、固定資産税などの明細を分類します。

平均比較は、総務省統計局の2024年家計調査にある単身世帯の月平均を、アプリのカテゴリに近い形へ対応させて使います。月表示では月平均、年表示では12倍した目安と比べます。節約ヒント右側の `平均との差を見る` ボタンを押すと、カテゴリごとの支出、平均、差額をポップアップの棒グラフで確認できます。平均値は見やすさのため100円未満を切り捨て、差額は実額で表示します。自己投資と資産形成は多いこと自体を問題にしないため、平均超過や節約助言の対象から外します。クレジットカードに出ない現金・口座引落分は含まれないため、生活全体の厳密な診断ではなく、カード明細上の目安として確認してください。

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
