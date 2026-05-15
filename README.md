### 利用前に
.env.example を コピーして .env にリネームし、環境依存の各種パラメータを入力してください。

#### .env 設定項目

| 項目 | 値の例 | 説明 | 
|---|---|---|
| BOT_PORT | 8000 | FastAPIでAPIを受け付ける場合のポート(まだ使わない) |
| DB_PORT | 5432 | Q&Aおよび埋め込みベクトルデータを保存するPostgreSQL DBコンテナのポート |
| DB_DIR | db_nomic | DBとして使うディレクトリ。embedding用のモデルを切り替える場合、埋め込み次元数の都合上テーブル定義が変わってくるので init.sql を可換とする。 |
| MODEL_EMBEDDING | text-embedding-nomic-embed-text-v1.5@q8_0 | embedding用のモデル名 |
| LMSTUDIO_EMBDDING_URL | http://host.docker.internal:1234/v1/embeddings | LM Studio 上の embedding用のモデルのエンドポイント |
| MODEL_CHAT | google/gemma-4-e4b | チャット作成用のモデル名 |
| LMSTUDIO_CHAT_URL | http://host.docker.internal:1234/v1/chat/completions | LM Studio 上の チャット作成用のモデルのエンドポイント |
