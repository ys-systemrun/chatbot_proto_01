# knowledge_mcp/ — ナレッジ検索・管理用 MCP サーバ

ナレッジ DB（`db_chatbot_knowledge_base`、PostgreSQL + pgvector）の QA・トラブルシューティング記事・タグを、MCP（Model Context Protocol）経由で検索・管理する独立サービスです（ADR-0001〜0006）。
`agent_invitro` が回答生成時の検索（`search_knowledge`）に、`web_backend`（管理 UI の BFF）が QA・タグ・言い換え質問文・トラブルシューティング記事の登録編集に利用します（ADR-0013）。

## サービスの要点

- **トランスポート**: Streamable HTTP（ADR-0002）。MCP エンドポイントは `/mcp`、ヘルスチェックは `GET /health`。既定ポート 8100（`KNOWLEDGE_MCP_PORT`）。
- **提供ツール**（定義は [`src/knowledge_mcp/mcp/tools.py`](src/knowledge_mcp/mcp/tools.py)）:
  - 検索: `search_knowledge` … QA とトラブルシューティング記事を横断する意味検索（ADR-0078）。`tags` は祖先タグ展開後のタグ構成類似度としてスコアに加味する（ADR-0058 / ADR-0059）。
  - タグ: `list_tags` / `create_tag` / `rename_tag` / `move_tag` / `reorder_tag` / `delete_tag` / `set_tag_description` / `add_tag_alias` / `update_tag_alias` / `remove_tag_alias` / `import_tag_batch` / `export_tags`（ADR-0006 / 0061 / 0065 / 0074 / 0080）
  - タグフォルダ: `set_tag_folder` / `list_tag_folders` / `create_tag_folder` / `rename_tag_folder` / `move_tag_folder` / `reorder_tag_folder` / `delete_tag_folder`（ADR-0072 / ADR-0073）
  - QA: `list_qa` / `get_qa` / `create_qa` / `update_qa` / `import_qa_batch` / `delete_qa` / `list_categories`（ADR-0014 / 0053 / 0067）
  - 言い換え質問文: `list_question_altered` / `get_question_altered` / `create_question_altered` / `update_question_altered` / `delete_question_altered` / `import_question_altered_batch` / `export_question_altered`（ADR-0064）
  - トラブルシューティング記事: `list_troubleshooting_articles` / `get_troubleshooting_article` / `update_troubleshooting_article` / `list_troubleshooting_source_keys`（ADR-0079）
- **DB**: `DATABASE_URL` で接続（アプリ用ロール `knowledge_app`、DML のみ）。主なテーブルは `hiroba_qa_original` / `hiroba_question_altered` / `hiroba_category` / `hiroba_qa_tag` / `tag` / `tag_alias` / `tag_folder` / `troubleshooting_article` / `troubleshooting_article_tag`。スキーマ作成・移行は `db_init` が担当し、本サービスは DDL を持たない。タグ等は内部にキャッシュせず都度 DB を参照する（ADR-0006）。
- **埋め込み**: `EMBEDDING_PROVIDER` で切り替え。`lmstudio`（既定。`LMSTUDIO_EMBEDDING_URL` / `MODEL_EMBEDDING`）または `bedrock`（AWS 環境。`BEDROCK_EMBEDDING_MODEL_ID` / `BEDROCK_REGION`、ADR-0031 / ADR-0102）。
- **起動**: `docker compose up -d knowledge_mcp`（ローカル）。コンテナ内では `python -m knowledge_mcp.main`。その他の環境変数（`KNOWLEDGE_MCP_DEFAULT_TOP_K`、`TAG_SIMILARITY_WEIGHT`、`SEARCH_CANDIDATE_POOL_SIZE` 等）は [`src/knowledge_mcp/mcp/server.py`](src/knowledge_mcp/mcp/server.py) とルートの `README.md` を参照。
- **テスト**: `knowledge_mcp/` で `pytest`（DB・外部 API 非依存の単体テスト）。

## 構成

| 名前 | 説明 |
|---|---|
| [`src/`](src/README.md) | Python パッケージ `knowledge_mcp` のソース（src レイアウト）。 |
| [`tests/`](tests/README.md) | pytest の単体テスト。Fake DB・モックで DB / 埋め込み API に依存せず検証する。 |
| [`.gitignore`](.gitignore) | `__pycache__/`・`*.pyc`・`.pytest_cache/`・`*.egg-info/`・`.venv/` を除外する。 |
| [`Dockerfile`](Dockerfile) | `python:3.11` ベースで本パッケージを `pip install -e .` し、`python -m knowledge_mcp.main` で起動するイメージ。healthcheck 用に curl を入れ、8100 番を公開する。ルートの `docker-compose.yml` と AWS（ECS Fargate, ADR-0024）のビルドで使う。 |
| [`pyproject.toml`](pyproject.toml) | パッケージ定義。依存（`mcp>=1.2.0,<2`・`psycopg2-binary`・`requests`・`uvicorn`・`boto3`）、コンソールスクリプト `knowledge-mcp`、dev 依存 `pytest` を定義する。 |
| [`依存関係メモ.drawio`](依存関係メモ.drawio) | 手書きの依存関係メモ（draw.io、未追跡ファイル）。「ページ2」は `main.py` → `mcp/server.py` の関係、「ページ3」は `db_init` 側のモジュール（`main.py`・`db.py`・`embedding.py`・`seed_helpers.py` 等）と JSON ファイル・LM Studio / Bedrock 接続の関係を描いたもの。 |

> `.pytest_cache/`・`__pycache__/`・`*.egg-info/` などは `.gitignore` 対象の生成物のため上表には載せていません。
