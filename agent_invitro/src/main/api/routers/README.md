# agent_invitro/src/main/api/routers — エンドポイント別ルーター

各モジュールが `APIRouter` を1つ持ち、パス・`response_model` の宣言、ユースケース関数の呼び出し、例外の `HTTPException` への変換だけを行います。ビジネスロジックは書きません（ADR-0090 決定3）。`app.py` の `create_app()` で登録されます。

## 構成

| 名前 | 説明 |
|---|---|
| [`__init__.py`](__init__.py) | パッケージ宣言。ルーターの方針を docstring に記す。 |
| [`ask_agentic.py`](ask_agentic.py) | `POST /ask-agentic`。`usecases/ask_agentic.py` を呼ぶ Agentic 探索ループ方式（ADR-0088 / ADR-0089）。 |
| [`ask_pipeline.py`](ask_pipeline.py) | `POST /ask-pipeline`。`usecases/ask_pipeline.py` を呼ぶ単発プロンプト生成方式（ADR-0043）。 |
| [`health.py`](health.py) | `GET /health`。ECS コンテナヘルスチェック用に `{"status": "ok"}` を返すだけ（DB・MCP・Bedrock は見ない）。 |
| [`release.py`](release.py) | `GET /release`。このプロセスのリリース（`build_release()` の結果）を返す。web_backend が未知の `release_id` を見たときに呼び、conversation DB の release テーブルへ登録する（ADR-0099 §1）。 |
