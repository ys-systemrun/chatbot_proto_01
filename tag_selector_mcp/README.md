# tag_selector_mcp/ — 質問文からタグを選ぶ MCP サーバ

質問文に最も関連する既存タグを選ぶ独立サービスです（ADR-0007〜0012）。タグの正本は Knowledge MCP が管理する `tag` テーブルで（ADR-0008）、`tag_alias`（同義語）と `tag.description` を使って選びます。
`agent_invitro`（質問のタグ付け）と `web_backend` の検証機能（ADR-0049）が MCP クライアントとして呼び出します。

## サービスの要点

- **トランスポート**: Streamable HTTP（ADR-0007）。MCP エンドポイントは `/mcp`、ヘルスチェックは `GET /health`。既定ポート 8200（`TAG_SELECTOR_MCP_PORT`）。
- **提供ツール**（定義は [`src/tag_selector_mcp/mcp/tools.py`](src/tag_selector_mcp/mcp/tools.py)）:
  - `select_tags` … 質問文に関連するタグを `id` / `name` / `score` / `path` で返す。`max_tags` / `confidence_threshold` / `alias_match_text`（ADR-0086）に対応。
  - `list_taxonomy` … キャッシュ中のタグ知識ベースを返す。
  - `reload_taxonomy` … タグ知識ベースを DB から再読込し件数を返す。
- **選択方式**（MVP, ADR-0009）: 同義語辞書との部分一致で「確定タグ」を決め（確定タグは優先して返す, ADR-0086）、残りは全タグを候補として LLM に選ばせる。埋め込みによる絞り込み・階層探索は未実装。
- **LLM**: `LLM_PROVIDER` で切り替え。`lmstudio`（既定。`LMSTUDIO_CHAT_URL` / `LMSTUDIO_CHAT_MODEL`）または `bedrock`（AWS 環境。`BEDROCK_CHAT_MODEL_ID` / `BEDROCK_REGION`、ADR-0031 / ADR-0102）。
- **DB**: `DATABASE_URL` でナレッジ DB（`db_chatbot_knowledge_base`）に読み取り専用の用途で接続し、`tag` と `tag_alias` を読む。DB への書き込みは行わない。Knowledge MCP と違い、タグ知識ベースは起動時ロード・定期ポーリング（`TAXONOMY_RELOAD_INTERVAL_SEC`、既定 300 秒）・`reload_taxonomy` でメモリにキャッシュする（ADR-0011）。
- **起動**: `docker compose up -d tag_selector_mcp`（ローカル）。コンテナ内では `python -m tag_selector_mcp.main`。既定値の環境変数（`TAG_SELECTOR_DEFAULT_MAX_TAGS` 等）は [`src/tag_selector_mcp/mcp/server.py`](src/tag_selector_mcp/mcp/server.py) とルートの `README.md` を参照。
- **テスト**: `tag_selector_mcp/` で `pytest`（DB・LLM 非依存の単体テスト）。

## 構成

| 名前 | 説明 |
|---|---|
| [`src/`](src/README.md) | Python パッケージ `tag_selector_mcp` のソース（src レイアウト）。 |
| [`tests/`](tests/README.md) | pytest の単体テスト。Fake DB・モック LLM で DB / LLM に依存せず検証する。 |
| [`.gitignore`](.gitignore) | `__pycache__/`・`*.pyc`・`.pytest_cache/`・`*.egg-info/`・`.venv/` を除外する。 |
| [`Dockerfile`](Dockerfile) | `python:3.11` ベースで本パッケージを `pip install -e .` し、`python -m tag_selector_mcp.main` で起動するイメージ。healthcheck 用に curl を入れ、8200 番を公開する。ルートの `docker-compose.yml` と AWS（ECS Fargate, ADR-0024）のビルドで使う。 |
| [`pyproject.toml`](pyproject.toml) | パッケージ定義。依存（`mcp>=1.2.0,<2`・`psycopg2-binary`・`requests`・`uvicorn`・`boto3`）、コンソールスクリプト `tag-selector-mcp`、dev 依存 `pytest` を定義する。 |

> `.pytest_cache/`・`__pycache__/`・`*.egg-info/` などは `.gitignore` 対象の生成物のため上表には載せていません。
