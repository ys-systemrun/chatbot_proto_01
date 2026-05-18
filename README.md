### 利用前に
1. LMStudio を立ち上げて chat用モデルとembedding用モデルをダウンロードしてください。.env.exampleでは仮に google_gemma-4-E4B-it-GGUF(google/gemma-4-e4b), Nomic-embed-text-v1.5-Embedding-GGUF(text-embedding-nomic-embed-text-v1.5@q8_0) をダウンロードするものとします。
2. .env.example を コピーして .env にリネームし、モデル名含む環境依存の各種パラメータを入力してください。
3. app\main\debug_question.py 内の ''' question:str = ''' の後ろ部分を任意の質問に変更し、debug_question を実行するとシーディング(不要な場合スキップ)および問い合わせに対する類似データ検索・回答生成の動作を確認できます。

#### .env 設定項目

| 項目 | 値の例 | 説明 | 
|---|---|---|
| BOT_PORT | 8000 | FastAPIでAPIを受け付ける場合のポート(まだ使わない) |
| DB_PORT | 5432 | Q&Aおよび埋め込みベクトルデータを保存するPostgreSQL DBコンテナのポート |
| DB_DIR | db_nomic | DBとして使うディレクトリ。embedding用のモデルを切り替える場合、埋め込み次元数の都合上テーブル定義が変わってくるので init.sql を可換とする。 ./{DB_DIR}/data 下には PostgreSQL のデータクラスタが構築される。 |
| CSV_DATA_DIR | data | 読み込むデータ内容を記述したCSVファイルやJSONファイルを配置したディレクトリ。 |
| QA_ORIGINAL_FILE | exportjson_withguid_small.json | オリジナルの質問・回答の組データのJSONファイル。(GUIDを付与したもの) |
| QUESTION_ALTERED_FILE | question_altered_small.csv | オリジナルと同様のことを違う聞き方で聞いた場合のパターン群。ChatGPTにより生成。 |
| CATEGORY_FILE | category.csv | 問い合わせを分類するカテゴリとそのコード値を記載したファイル。 |
| MODEL_EMBEDDING | text-embedding-nomic-embed-text-v1.5@q8_0 | embedding用のモデル名 |
| LMSTUDIO_EMBDDING_URL | http://host.docker.internal:1234/v1/embeddings | LM Studio 上の embedding用のモデルのエンドポイント |
| MODEL_CHAT | google/gemma-4-e4b | チャット作成用のモデル名 |
| LMSTUDIO_CHAT_URL | http://host.docker.internal:1234/v1/chat/completions | LM Studio 上の チャット作成用のモデルのエンドポイント |
