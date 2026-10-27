# web_backend/src/main/controllers/ — 各 API ルートのレスポンス生成ロジック

`app.py` のルートから呼ばれる Controller 群。ルート定義は薄く保ち、処理の実体はここに置く。管理UI系はナレッジ DB に直接書き込まず Knowledge MCP 経由で処理する（ADR-0013）。チャットは agent_invitro への中継（ADR-0045 / ADR-0089）とローカル直接処理に分かれる。

## 構成

| 名前 | 説明 |
|---|---|
| [`__init__.py`](__init__.py) | パッケージ宣言用の空ファイル。 |
| [`agent_controller.py`](agent_controller.py) | `/api/ask-pipeline`・`/api/ask-agentic` を agent_invitro の `/ask-pipeline`（ADR-0043）・`/ask-agentic`（ADR-0088）へ中継し、`/api/release` で現在のリリースを返す。回答に付いたリリースを conversation DB へ登録する（ADR-0099）。 |
| [`chat_controller.py`](chat_controller.py) | `/api/ask-local` のローカル直接処理。LM Studio で要約・検索クエリ生成→埋め込み→類似検索→回答生成を行い、`src/log` に記録する。ローカル docker-compose 向けで UI からは呼ばれない。 |
| [`chat_schemas.py`](chat_schemas.py) | 3 つの ask ルートが共有するリクエスト・レスポンス等の Pydantic スキーマ。`agent_invitro/src/main/api/schemas.py` と同一契約で、片方だけ変更してはならない。 |
| [`evaluation_controller.py`](evaluation_controller.py) | `/api/evaluate_response`（会話・メッセージと評価の upsert）と `/api/evaluated_messages`（評価済み会話一覧）を `ConversationDB` で処理する。 |
| [`export_controller.py`](export_controller.py) | `/api/export` の処理。DB 接続を開き、`src/export` でテーブルを CSV/SQL 化して ZIP にまとめ、ファイル名（Asia/Tokyo タイムスタンプ）を付けてエクスポートをログに記録する。 |
| [`qa_controller.py`](qa_controller.py) | `/api/qa*`・`/api/categories` の処理。QA の一覧・詳細・作成・更新・削除・CSV インポートとカテゴリ一覧を Knowledge MCP 経由で行う。 |
| [`question_altered_controller.py`](question_altered_controller.py) | `/api/hiroba_question_altered*` の処理。言い換え行（is_primary=false）の一覧・詳細・作成・編集・削除・CSV インポート／エクスポートを Knowledge MCP 経由で行う（ADR-0064）。 |
| [`tag_controller.py`](tag_controller.py) | `/api/tags*`・`/api/tag-folders*` の処理。タグ・別名・タグフォルダの CRUD、並び替え、CSV インポート／エクスポートを Knowledge MCP のタグ管理ツール経由で行う。 |
| [`troubleshooting_controller.py`](troubleshooting_controller.py) | `/api/troubleshooting_articles*` の処理。トラブルシューティング記事の一覧・詳細・更新（構造化フィールド編集＋タグ付け）を Knowledge MCP 経由で行う（ADR-0079。作成・削除はなし）。 |
| [`verification_controller.py`](verification_controller.py) | `/api/verification/*` の処理。検証質問の CRUD と CSV 一括インポート、検証実行（Tag Selector MCP の select_tags → Knowledge MCP の search_knowledge）、評価保存を `VerificationDB` に対して行う（ADR-0048 / ADR-0049 / ADR-0054）。 |
