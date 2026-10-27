# web_backend/src/main/ — FastAPI アプリのルート定義・設定・CLI スクリプト

web_backend の全 API ルートを定義する `app.py`（エントリポイント `src.main.app:app`）と、その処理を担う Controller 群、環境設定をまとめたフォルダ。あわせて、pyproject の `[project.scripts]` に登録された評価・デバッグ用 CLI と、初期の対話型チャット実装も置かれている。

## 構成

| 名前 | 説明 |
|---|---|
| [`controllers/`](controllers/README.md) | 各ルートのレスポンス生成ロジック（チャット中継・ローカル処理、会話評価、QA・タグ・言い換え・トラブルシューティング管理、検証、エクスポート）。 |
| [`__init__.py`](__init__.py) | パッケージ宣言用の空ファイル。 |
| [`app.py`](app.py) | 全ルート定義を集約した唯一のファイル。`/api/ask-pipeline`・`/api/ask-agentic`・`/api/ask-local`・`/api/release`、評価、`/api/qa*`・`/api/tags*`・`/api/tag-folders*`・`/api/hiroba_question_altered*`・`/api/troubleshooting_articles*`・`/api/verification/*`・`/api/export`・`/health` を定義し、`STATIC_DIR` があれば SPA の静的配信とフォールバックも登録する（ADR-0042）。 |
| [`chat.py`](chat.py) | ターミナルで対話する初期の CLI チャット。類似検索→適合判定（`--relevance` で距離／LLM を選択）→回答生成を行い、`write_chat` でセッションログを残す。 |
| [`config.py`](config.py) | `app.py` と Controller が参照する環境変数（DB 接続先、LM Studio、agent_invitro・Knowledge MCP・Tag Selector MCP の URL、検証パラメータ、`STATIC_DIR` など）を集約したモジュール。 |
| [`debug.py`](debug.py) | スクリプト内に固定した質問で埋め込み→類似検索→回答生成を一通り実行する自由デバッグ用 CLI（`debug` コマンド）。 |
| [`debug_question.py`](debug_question.py) | `debug.py` と同様に、スクリプト内の質問で類似検索から回答生成までを確認するデバッグ用 CLI（`debug_question` コマンド）。 |
| [`evaluate.py`](evaluate.py) | 検索精度の評価 CLI（`evaluate` コマンド）。正解 QA 付きクエリ CSV から MRR を、ノイズクエリ CSV から距離閾値による TNR を計算し、任意でクエリ別結果を CSV 出力する。 |
| [`main.py`](main.py) | 旧 stateful 版の FastAPI アプリ。`InMemorySessionStore` で会話状態を保持し、`POST /ask` と `DELETE /session/{id}` を提供する。現在のエントリポイントではない。 |
| [`状態遷移.drawio`](状態遷移.drawio) | `chat.py` の CLI チャットの状態遷移図（入力待ち・exit/quit・EOF/中断・回答生成の流れ）。 |
