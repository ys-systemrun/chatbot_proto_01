# agent_invitro/src/main/api — FastAPI の HTTP サーバー

AWS 環境で `admin_ui`（web_backend）から VPC 内部通信で呼ばれる常駐 HTTP サーバーです（ADR-0043）。スキーマ・依存の組み立て・ルーターだけを持ち、実処理は `usecases/` にあります（ADR-0090）。ローカル docker-compose では起動しません。

## 構成

| 名前 | 説明 |
|---|---|
| [`routers/`](routers/README.md) | エンドポイントごとの薄い `APIRouter`（health / ask-pipeline / ask-agentic / release）。 |
| [`__init__.py`](__init__.py) | パッケージ宣言（空）。 |
| [`app.py`](app.py) | `create_app()`: FastAPI を生成し、ルーターを登録してロギングを設定する。import 時の副作用を持たない。 |
| [`dependencies.py`](dependencies.py) | `get_components()`: 設定読み込み・MCP ツール取得・Bedrock 各クライアント生成を最初のリクエスト時に一度だけ行い、キャッシュして各ルーターへ渡す（ADR-0090 決定6）。 |
| [`schemas.py`](schemas.py) | API 契約 `Message` / `Summary` / `Request` / `Response`。両 ask エンドポイント共通で、web_backend の `chat_controller.py` の同名モデルと同一契約（ADR-0089 決定2）。 |
| [`server.py`](server.py) | 起動エントリポイント。`app = create_app()` のみ。Terraform の起動コマンドが参照するため名前を変えない（ADR-0090 決定2）。 |
