# db_init/ — DB マイグレーション & シードのワンショットサービス

knowledge データベース（維津美の広場 QA・タグ・トラブルシューティング記事）と conversation データベース（会話・評価・検証）の
スキーマ作成（yoyo マイグレーション, ADR-0017 / ADR-0051）・用途別ロールの作成（ADR-0052）・初期データ投入（冪等シード, ADR-0018）を
1 回実行して終了するコンテナです。ローカルでは `docker compose up` で、AWS では ECS タスクとして起動されます。
起動時の環境変数で、全データインポート（`IMPORT_MODE`, ADR-0066）・アドホック SQL 実行（`QUERY_MODE`, ADR-0083）・
退避エクスポート（`EXPORT_MODE`, ADR-0103）・スキーマ反映のみ（`MIGRATE_ONLY`, ADR-0075）にも切り替わります。

## 構成

| 名前 | 説明 |
|---|---|
| [`data/`](data/README.md) | シード元データ（DVC 管理, ADR-0097）。イメージに `/data` として同梱される（ADR-0034） |
| [`migrations/`](migrations/README.md) | knowledge データベースの yoyo マイグレーション（0001〜） |
| [`migrations_conversation/`](migrations_conversation/README.md) | conversation データベースの yoyo マイグレーション（0001〜） |
| [`src/`](src/README.md) | エントリポイント `main.py` とシード・インポート・エクスポート処理 |
| [`tests/`](tests/README.md) | `src/` の純関数の単体テスト（pytest。DB・S3・embedding には触れない） |
| [`tools/`](tools/redmine_wiki_to_csv.py) | シード元データを作るための 1 回限りの加工ツール。`redmine_wiki_to_csv.py` は Redmine Wiki の保存 HTML を `data/redmine_error_taiou/` の CSV に変換する（顧客名の伏せ字を含む, ADR-0105）。`hiroba_qa_json_to_csv.py` は広場 QA 本体の JSON を `data/hiroba_qa/hiroba_qa_original.csv` に、`troubleshooting_html_to_csv.py` はトラブルシューティング記事の HTML を `data/troubleshooting/*.csv` に変換する。`normalize_csv.py` は CSV を ADR-0108 の書式に書き直す（列名の変更も可）（いずれも ADR-0108）。シードからは呼ばない |
| [`.dockerignore`](.dockerignore) | 加工前の元データ（`data/error_taiou_o/`）をイメージに入れない |
| [`Dockerfile`](Dockerfile) | python:3.11 ベースのイメージ。手動リカバリ用に `psql`・`aws` CLI を同梱し、`data/` を `/data` に焼き込む。既定 CMD は `python src/main.py` |
| [`pyproject.toml`](pyproject.toml) | 依存パッケージ（psycopg2-binary・requests・yoyo-migrations・boto3・beautifulsoup4）の定義。`src/` はスクリプトとして直接実行するためパッケージは持たない |
| [`依存関係メモ.drawio`](依存関係メモ.drawio) | `src/main.py` から `backfill_title_and_tags.py`・`db.py`・`embedding.py`・`models.py`・`seed_*.py` への呼び出し関係と、JSON ファイル・LM Studio / Bedrock への接続を描いたメモ図（draw.io） |
