### 利用前に
1. LMStudio を立ち上げて chat用モデルとembedding用モデルをダウンロードしてください。.env.exampleでは仮に google_gemma-4-E4B-it-GGUF(google/gemma-4-e4b), Nomic-embed-text-v1.5-Embedding-GGUF(text-embedding-nomic-embed-text-v1.5@q8_0) をダウンロードするものとします。その後、Ctrl + 2 でDevelopper画面に移動し、上部のトグルで LM Studio Local Serve を Running にし、Load Model ボタンでダウンロードした2つのモデルをロードしてください。
2. .env.example を コピーして .env にリネームし、モデル名含む環境依存の各種パラメータを入力してください。
3. app\main\debug_question.py 内の ''' question:str = ''' の後ろ部分を任意の質問に変更し、debug_question を実行するとシーディング(不要な場合スキップ)および問い合わせに対する類似データ検索・回答生成の動作を確認できます。

#### .env 設定項目

| 項目 | 値の例 | 説明 | 
|---|---|---|
| BOT_PORT | 8000 | FastAPI がリクエストを受け付けるポート |
| FRONT_PORT | 5173 | デバッグ UI (Vite dev server) の対ホストポート |
| DB_PORT | 5432 | Q&Aおよび埋め込みベクトルデータを保存するPostgreSQL DBコンテナの対ホストポート |
| DB_DIR | db_nomic | DBとして使うディレクトリ。embedding用のモデルを切り替える場合、埋め込み次元数の都合上テーブル定義が変わってくるので init.sql を可換とする。 ./{DB_DIR}/data 下には PostgreSQL のデータクラスタが構築される。 |
| CSV_DATA_DIR | data | 読み込むデータ内容を記述したCSVファイルやJSONファイルを配置したディレクトリ。 |
| QA_ORIGINAL_FILE | exportjson_withguid_small.json | オリジナルの質問・回答の組データのJSONファイル。(GUIDを付与したもの) |
| QUESTION_ALTERED_FILE | question_altered_small.csv | オリジナルと同様のことを違う聞き方で聞いた場合のパターン群。ChatGPTにより生成。 |
| CATEGORY_FILE | category.csv | 問い合わせを分類するカテゴリとそのコード値を記載したファイル。 |
| MODEL_EMBEDDING | text-embedding-nomic-embed-text-v1.5@q8_0 | embedding用のモデル名 |
| LMSTUDIO_EMBDDING_URL | http://host.docker.internal:1234/v1/embeddings | LM Studio 上の embedding用のモデルのエンドポイント |
| MODEL_CHAT | google/gemma-4-e4b | チャット作成用のモデル名 |
| LMSTUDIO_CHAT_URL | http://host.docker.internal:1234/v1/chat/completions | LM Studio 上の チャット作成用のモデルのエンドポイント |
| EVAL_QUERIES_CSV | eval_queries.csv | 評価用のクエリ:正解の qa_id の組 |

## デバッグ UI による動作確認

`front_dev/` に含まれる TypeScript + Vite 製のシンプルな UI を使って、バックエンドの動作をブラウザから確認できます。

### 前提条件

以下がすべて満たされている状態で進めてください。

- LMStudio が起動しており、chat 用・embedding 用の両モデルが **Load** されている
- `.env` を `.env.example` からコピーして編集済みである
- DB のシーディングが完了している（初回のみ。後述「シーディング」参照）

### 起動

プロジェクトルートで以下を実行します。

```bat
REM Windows
build.bat
```

```bash
# Unix / WSL
docker compose up -d --build
```

3 つのコンテナ（`chatbot_db` → `chatbot_app` → `chatbot_frontend`）が順に起動します。  
初回は `npm install` を含むビルドが走るため数分かかります。

起動状況は以下で確認できます。

```bash
docker compose ps
docker compose logs -f frontend   # Vite の起動ログ
docker compose logs -f app        # FastAPI の起動ログ
```

`chatbot_frontend` のログに `Local: http://localhost:5173/` が表示されれば準備完了です。

### ブラウザからアクセス

```
http://localhost:5173
```

ポートを変更した場合は `.env` の `FRONT_PORT` の値に合わせてください。

### 動作確認手順

#### 1. 質問を送信する

テキストエリアに製品に関する質問を入力し、「送信」ボタンまたは **Ctrl+Enter** を押します。

#### 2. Session ID の発行を確認する

初回送信後、ヘッダーの **Session ID** 欄に UUID が表示されます。  
この値がバックエンドで管理されるセッションキーです。

#### 3. アシスタントの回答を確認する

アシスタントのメッセージが表示されます。  
回答の下にある **「API レスポンス (JSON)」** を展開すると、バックエンドからの生レスポンスを確認できます。

```json
{
  "session_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "answer": "お問い合わせいただきありがとうございます。..."
}
```

#### 4. 会話の継続を確認する

続けて別の質問を送信し、ヘッダーの Session ID が **変わらず同じ値**のままであることを確認します。  
これにより、会話履歴が同じセッションに蓄積されていることが分かります。

#### 5. セッションリセットを確認する

「**セッションリセット**」ボタンを押すと、以下が行われます。

- `DELETE /session/{session_id}` がバックエンドに送信される
- 画面の会話履歴がクリアされる
- Session ID 表示が「（未開始）」に戻る

次の送信で新しい Session ID が発行されれば、リセットが正常に機能しています。

### トラブルシューティング

| 症状 | 確認箇所 |
|---|---|
| `http://localhost:5173` に繋がらない | `docker compose ps` で `chatbot_frontend` が `Up` か確認。`docker compose logs frontend` でエラーを確認 |
| 質問を送ると `502 Bad Gateway` が返る | `chatbot_app` が起動しているか確認。`docker compose logs app` を参照 |
| 回答が返らず長時間待機になる | LMStudio でモデルがロードされているか確認 |
| `Session ID` が毎回変わる | `chatbot_app` が再起動している可能性あり。`InMemorySessionStore` はプロセス再起動でデータが失われる |

---

## 評価 (MRR)

このリポジトリには、データベースの類似検索 `DB.search_similar` の性能指標として MRR (Mean Reciprocal Rank) を計測するスクリプトがあります。

- 評価用 CSV: `data/eval_queries.csv`（ヘッダ例: `query,qa_id`）
- 環境変数: `EVAL_QUERIES_CSV` にコンテナ内の CSV パスを指定できます。コンテナ実行時に `.env` 経由で注入してください。


例: `.env` を作成（`.env.example` をコピーして編集）

```bash
# Unix / WSL
cp .env.example .env

# PowerShell
Copy-Item .env.example .env
```

次に `.env` を開き、以下の環境変数を設定してください:

```
EVAL_QUERIES_CSV=eval_queries.csv
DATABASE_URL=postgresql://user:pass@host:5432/dbname
LMSTUDIO_EMBEDDING_URL=http://host.docker.internal:1234/v1/embeddings
MODEL_EMBEDDING=text-embedding-nomic-embed-text-v1.5@q8_0
```

実行方法:

- 開発インストールしてプロジェクトスクリプトを使う方法（推奨、一度だけ）:

```bash
python -m pip install -e app
evaluate
```

- 直接モジュールを実行する方法:

```bash
python -m main.evaluate --top-k 10 --output /tmp/results.csv
```

実行時は `DATABASE_URL`, `LMSTUDIO_EMBEDDING_URL`, `MODEL_EMBEDDING` が環境に設定されている必要があります。出力に MRR が表示され、`--output` でクエリごとの順位情報を CSV に保存できます。

