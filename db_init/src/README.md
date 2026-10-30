# db_init/src — db_init の処理本体

`python src/main.py` で起動されるスクリプト群です（パッケージではなく、同じディレクトリのモジュールを直接 import する）。
シード関連の多くは web_backend・knowledge_mcp・tag_selector_mcp から移管したもので、コードは共有せず db_init 独自に持っています（ADR-0016〜0018）。

## 構成

| 名前 | 説明 |
|---|---|
| [`main.py`](main.py) | エントリポイント。ロール作成（ADR-0052）→ knowledge マイグレーション → シード → 権限付与 → conversation DB の作成・マイグレーション → エクスポート用読み取りロール作成、を順に実行する。`MIGRATE_ONLY` / `IMPORT_MODE` / `QUERY_MODE` / `EXPORT_MODE` で起動モードを切り替える |
| [`db.py`](db.py) | シード投入用の DB アクセス（カテゴリ・QA・言い換え質問文の存在チェックと INSERT）。テーブル単位の存在チェックで冪等にする（ADR-0018） |
| [`models.py`](models.py) | シード対象のデータクラス（`Category`・`QAOriginal`・`QuestionAltered`） |
| [`seed_helpers.py`](seed_helpers.py) | シード元データ（カテゴリ CSV・QA JSON・言い換え CSV）の読み込み |
| [`embedding.py`](embedding.py) | シード時の embedding 計算。`EMBEDDING_PROVIDER` で LM Studio（OpenAI 互換 API）と Amazon Bedrock を切り替える（ADR-0031） |
| [`backfill_title_and_tags.py`](backfill_title_and_tags.py) | QA JSON から `title` を補完し、レコードにタグがあれば `tag`・`hiroba_qa_tag` に投入する（冪等。現行データにはタグが無く title のみ補完） |
| [`seed_description_and_aliases.py`](seed_description_and_aliases.py) | 一部タグの説明文と同義語（`tag_alias`）の暫定シード（Tag Selector MCP の動作確認用） |
| [`troubleshooting_import.py`](troubleshooting_import.py) | トラブルシューティング記事 HTML を `<h2>` 単位に分割・構造化し（ADR-0076）、整形済み CSV は 1 行 = 1 記事として読んで（ADR-0105）、`troubleshooting_article` に冪等投入する |
| [`import_data.py`](import_data.py) | `IMPORT_MODE` の全データインポート。事前バックアップを S3 に置き、対象テーブルを TRUNCATE して S3 の SQL ダンプを同一トランザクションで投入する（ADR-0066） |
| [`export_data.py`](export_data.py) | `EXPORT_MODE` の退避エクスポート。読み取り専用トランザクションで全対象テーブルを SQL（TRUNCATE + INSERT）とマニフェストにして S3 に置く（ADR-0103, destroy-all / export-data から使用） |
