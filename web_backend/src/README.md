# web_backend/src/ — web_backend アプリ本体のパッケージ

FastAPI アプリ（`main/app.py`）と、それが使う DB アクセス・MCP クライアント・LLM 呼び出し・ログ出力などの部品をまとめたパッケージ。`from src.xxx import ...` の形で参照される。

## 構成

| 名前 | 説明 |
|---|---|
| [`conversation_db/`](conversation_db/README.md) | conversation データベースの会話・メッセージ・リリースの upsert／取得（会話評価機能・agent_invitro 中継が使用）。 |
| [`export/`](export/README.md) | 全データエクスポート（`GET /api/export`）用の CSV／SQL ダンプ生成と ZIP 化（ADR-0046 / ADR-0047）。 |
| [`keyword/`](keyword/README.md) | 質問文からキーワードを抽出する部品（語彙リスト版・LLM 版）。現在 web_backend 内に呼び出し元はない。 |
| [`llm/`](llm/README.md) | LM Studio／Bedrock を使った回答生成・会話要約・検索クエリ生成のクラスと旧プロンプト関数。 |
| [`log/`](log/README.md) | 検索・回答生成・管理UI操作・エクスポートを日付別 JSONL に記録するロガー。 |
| [`main/`](main/README.md) | FastAPI のルート定義（`app.py`）、Controller 群、環境設定、CLI／デバッグ用スクリプト。 |
| [`mcp_client/`](mcp_client/README.md) | Knowledge MCP・Tag Selector MCP を呼び出す MCP クライアントラッパー。 |
| [`models/`](models/README.md) | QA・カテゴリ・言い換えのデータクラスと、会話状態・メッセージのモデル。 |
| [`relevance/`](relevance/README.md) | 類似検索結果が質問に適合するかを判定するストラテジー（距離閾値・LLM 判定）。CLI チャットが使用。 |
| [`session/`](session/README.md) | 会話状態（`ConversationState`）をセッション ID で保持するストア（メモリ／ファイル／Redis）。旧 stateful アプリが使用。 |
| [`verification_db/`](verification_db/README.md) | 検証機能（質問→タグ→情報源）の `verification_*` テーブルへの読み書き（ADR-0048）。 |
| [`__init__.py`](__init__.py) | パッケージ宣言用の空ファイル。 |
| [`db.py`](db.py) | ナレッジ DB への接続クラス `DB`。pgvector のコサイン距離で `hiroba_question_altered` を類似検索し、元 QA の質問・回答と結合して返す（`search_similar`）。ローカル直接処理チャットや評価・デバッグスクリプトが使用。 |
| [`embedding.py`](embedding.py) | 埋め込み API（LM Studio の OpenAI 互換エンドポイント）にテキストを送りベクトルを得る `get_embedding`。 |
| [`write_chat.py`](write_chat.py) | CLI チャット（`main/chat.py`）のセッションログを `web_backend/logs/chat_YYYYMMDD_HHMMSS.log` に書き出すモジュール（ユーザー入力・検索結果・回答・会話状態をターンごとに追記）。 |

`__pycache__/` は .gitignore 対象のため載せていない。
