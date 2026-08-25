# ADR-0047: 全データエクスポート機能のダンプ生成方式・配信方式（SQL/CSV、同期ストリーミングダウンロード）

- ステータス: Accepted
- 日付: 2026-08-24
- 関連: `docs/requirement/202608241530_全データエクスポート機能要件定義書.md`, ADR-0013, ADR-0015, ADR-0042, ADR-0044, ADR-0046

## コンテキスト

ADR-0046により、`admin_ui`（`web_backend`）は `chatbot` データベース（読み取り専用ロール、新設）・`conversation` データベース（既存の `CONVERSATION_DB_URL`）の両方に対して、対象8テーブル（`qa_original` / `question_altered` / `category` / `tag` / `tag_alias` / `qa_tag` / `conversation` / `message`）を読み取れるようになった。本ADRでは、これらのデータをブラウザのボタンクリックから「SQL」または「CSV」としてダウンロードさせるための、具体的な生成方式・ファイル構成・配信方式を決定する。

`admin_ui` は `front_dev` の本番ビルド資産と `web_backend`（FastAPI）を単一コンテナ・単一ECS Fargateサービスとして配信する構成であり（ADR-0042）、S3・CloudFrontや専用のジョブキュー等の追加インフラは意図的に見送られてきた（ADR-0042「検討した代替案」）。エクスポート対象のデータ量は、QAナレッジベース（既存READMEのシードデータ規模）と会話評価ログ（ADR-0044時点で保持期間ポリシー未確定、Open Issue）であり、現時点では大規模ではないが、`conversation`/`message` は運用継続に伴い増加し得る。

## 決定

**`pg_dump` / `psql` 等の外部コマンドは使わず、`web_backend` が既に利用しているDBドライバ（`psycopg2`）でテーブルを直接読み取り、アプリケーションコード内でSQL文字列またはCSVを組み立てる。生成したファイルは常にZIPアーカイブ1個にまとめ、非同期ジョブ化やS3への一時保管を行わず、HTTPレスポンスとして同期的にストリーミング配信する。**

1. **エンドポイント**: `web_backend` に `GET /api/export?format=sql|csv` を新設する。`format` はクエリパラメータで指定し、他の `/api/*` エンドポイントと同様に `front_dev` からは同一オリジン（ALB経由）で呼び出す。
2. **データ取得**: 各テーブルについて `COPY (SELECT * FROM <table> ORDER BY <主キー>) TO STDOUT WITH CSV HEADER` を `psycopg2.copy_expert` で実行し、サーバー側でカーソルを保持しながらストリーム的に読み出す（テーブル全体を一度にPythonのメモリへ展開しない）。`chatbot` データベースへは ADR-0046 の `CHATBOT_EXPORT_DB_URL`（読み取り専用ロール）、`conversation` データベースへは既存の `CONVERSATION_DB_URL` で接続する。
3. **CSV形式**: テーブルごとに1ファイル（`qa_original.csv`, `question_altered.csv`, `category.csv`, `tag.csv`, `tag_alias.csv`, `qa_tag.csv`, `conversation.csv`, `message.csv`）とし、8ファイルをZIPアーカイブにまとめて返す。**`question_altered.csv` には `embedding` 列を含めない**（CSVは人がExel等で内容を確認する用途を主眼とし、768/1536次元の浮動小数点配列を1セル文字列として含めると可読性・ファイルサイズの両面で実用的でないため）。
4. **SQL形式**: データベースごとに1ファイル（`chatbot.sql`, `conversation.sql`）とし、2ファイルをZIPアーカイブにまとめて返す。各ファイルは、既存のスキーマ定義（`db_hiroba_qa_init/migrations/`、`db_conversation/init.sql`）と同一のテーブル定義を冪等な `CREATE TABLE IF NOT EXISTS` として先頭に含め、続けて取得した全行を `INSERT INTO <table> (...) VALUES (...);`（バッチサイズは実装フェーズで決定、例: 500行単位のマルチ行INSERT）として出力する。`question_altered.embedding` は、SQL形式では**含める**（バックアップ・他環境への再構築を主目的とするため、`pgvector` の `VECTOR` リテラル表記で出力し、`psql -f` でそのまま再投入できる形にする）。
5. **ファイル名・タイムスタンプ**: ZIPのファイル名は `chatbot_invitro_export_<YYYYMMDDHHmmss>_<format>.zip` とし、生成時刻をUTCまたはJSTのいずれかで統一する（実装フェーズで確定、既存ログ・タイムスタンプ規約に合わせる）。
6. **配信**: FastAPIの `StreamingResponse`（`Content-Type: application/zip`, `Content-Disposition: attachment; filename=...`）でそのままHTTPレスポンスとして返す。S3への一時保存や署名付きURLの発行は行わない。バックグラウンドジョブ化（非同期実行＋ポーリング）も行わない。
7. **フロントエンド**: `front_dev` の `/admin/export` に新規ページを追加する（ADR-0015のルーティング方針を踏襲、`/admin` サブツリー限定）。「SQL」「CSV」のいずれかを選択するラジオボタンと「エクスポート」ボタンを配置し、クリックで `GET /api/export?format=...` を呼び出し、レスポンスのBlobを `URL.createObjectURL` 等でブラウザのファイル保存ダイアログにつなげる。処理中は多重クリック防止のためボタンを無効化し、完了・失敗を画面上に表示する。

## 検討した代替案

- **`pg_dump` / `psql` を子プロセスとして呼び出す**: 標準的なダンプ形式が得られる利点があるが、`web_backend` のコンテナイメージ（`python:3.11` ベース、ADR-0042で既にNode.jsビルドステージの追加のみに抑える判断をしている）にPostgreSQLクライアントツール一式を追加する必要が生じ、依存関係が増える。また `pg_dump` はテーブル所有者・カタログ情報への広めのアクセス（`--data-only` 指定時も対象テーブルの読み取り権限に加えカタログ参照が発生する）を前提にすることが多く、ADR-0046で新設した最小権限（SELECTのみ）ロールとの相性を都度検証する手間が増える。ローカル（Windows/WSL上のDocker Desktop）とAWS（ECS Fargate、Linux）で子プロセスの挙動・エラーハンドリングを揃える検証コストも発生するため、既存のDBドライバで完結する方式を優先し不採用とした。
- **非同期ジョブ化 + S3一時保管 + 署名付きURL方式**: `conversation`/`message` が将来大きく増加した場合や、ALB/ゲートウェイのタイムアウト（数十秒〜数分）に抵触するリスクを避けられる利点があるが、現時点のデータ規模（QAナレッジベース、README記載のシード規模）では同期処理で十分と判断した。S3バケットの新設・ライフサイクル管理・署名付きURLの有効期限設計など、ADR-0042が「本フェーズの規模に対しては過大」として見送ったS3+CloudFront案と同種の懸念があるため、本フェーズでは見送る。将来のデータ量次第で本ADRを見直す（12章相当のOpen Issueとして要件定義書に記載）。
- **CSVにも `embedding` 列を含める（完全な列互換を優先）**: SQL・CSVで含める列を統一できる一貫性はあるが、Excel等での閲覧・分析というCSV利用シーンに対して768/1536次元の配列文字列は実用性が低く、ファイルサイズも大きくなる。SQL側で完全な再構築可能性を担保していることから、CSV側は可読性を優先し除外することとした。将来、CSV側にも埋め込みベクトルの再現性が必要になった場合は、`--include-embedding` のようなオプションを別途追加することを妨げない。
- **テーブルごとに個別のダウンロードボタンを用意する（ZIP化しない）**: 「全データをエクスポートする」という要件（ボタン一つで完結させたいという発注者の意図）に対して、8回のダウンロード操作を利用者に強いることになり、UXとして本フェーズの目的に合わない。ZIPアーカイブ1個への集約を優先した。

## 結果・影響

- `web_backend` に新規エンドポイント（`GET /api/export`）とダンプ生成モジュール（テーブル定義・カラムリストを持つ設定＋CSV/SQL組み立てロジック）が追加される。既存の `/api/qa/*`, `/api/tags/*`, `/evaluate_response` 等の実装には変更を加えない。
- `front_dev` に新規ページ（`/admin/export`）とAPI呼び出し・ファイルダウンロード処理が追加される。既存のQA一覧・タグ階層等の画面には影響しない。
- コンテナイメージへの新規バイナリ依存（PostgreSQLクライアントツール等）は発生しない。
- 大量データ・長時間実行によるタイムアウトリスクは、現時点のデータ規模では顕在化しないと想定するが、`conversation`/`message` の保持期間ポリシー（ADR-0044のOpen Issue）が確定しないまま長期間データが蓄積した場合、本ADRの同期配信方式を非同期方式へ見直す必要が生じ得る。要件定義書のOpen Issueとして引き継ぐ。
- ダンプに個人情報・機微情報を含み得る会話ログ（`conversation`/`message`）がそのままZIPファイルとして利用者のブラウザ・ローカルディスクへダウンロードされる点は、既存のADR-0044が指摘した会話データの取り扱い上の論点をエクスポート機能にも引き継ぐ（要件定義書の非機能要件・Open Issue参照）。
