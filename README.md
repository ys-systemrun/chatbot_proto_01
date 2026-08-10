### 利用前に
1. LMStudio を立ち上げて chat用モデルとembedding用モデルをダウンロードしてください。.env.exampleでは仮に google_gemma-4-E4B-it-GGUF(google/gemma-4-e4b), Nomic-embed-text-v1.5-Embedding-GGUF(text-embedding-nomic-embed-text-v1.5@q8_0) をダウンロードするものとします。その後、Ctrl + 2 でDevelopper画面に移動し、上部のトグルで LM Studio Local Serve を Running にし、Load Model ボタンでダウンロードした2つのモデルをロードしてください。
2. .env.example を コピーして .env にリネームし、モデル名含む環境依存の各種パラメータを入力してください。`DB_DIR` に対応した `EMBEDDING_VECTOR_DIM`（`db_nomic` なら 768、`db_multilingual` なら 384）を必ず設定してください。
3. `docker compose up` を実行してください。スキーマ作成（マイグレーション）と初期データ投入（シード、embedding計算を含む）は、専用のワンショットサービス `db_hiroba_qa_init` が自動的に実行します（IMPL-202608061016 / ADR-0016〜0018）。手動でのシーディング操作は不要です。既存データが投入済みの場合は、テーブル単位の存在チェックにより自動的にスキップされます。

> **注意**: シードは `question_altered` の各行について LM Studio の embedding エンドポイントを呼び出します。`docker compose up` の前に LM Studio を起動し、embedding 用モデルをロードしておいてください。未起動のままだと `db_hiroba_qa_init` がシードに失敗し（非0終了）、これに依存する `web_backend` / `knowledge_mcp` / `tag_selector_mcp` は起動しません。ログは `docker compose logs db_hiroba_qa_init` で確認できます。

#### 既存環境（手動 migration 適用済みボリューム）からの移行

既に旧方式（`db_nomic/init.sql` ＋ `knowledge_mcp/migrations/` 等の手動適用）でスキーマを構築済みの既存 `db_nomic/data` を使う場合、`db_hiroba_qa_init` の全マイグレーションSQLは `IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS` でガードされているため、**そのまま `docker compose up` しても既存テーブル・列に対して無害に完了します**（未追跡のマイグレーションを yoyo が再実行しても、実体は作成済みのためスキップと同義）。

マイグレーションを「適用済み」として yoyo の追跡テーブルに明示登録（ベースライン化）したい場合は、`yoyo mark` を利用できます。

```bash
# 実行前に LM Studio 等は不要（マイグレーション履歴の登録のみ）。既存の全ステップを適用済みとして記録する。
docker compose run --rm db_hiroba_qa_init \
  yoyo mark --batch --database "postgresql://postgres:postgres@db_hiroba_qa:5432/chatbot" ./migrations
```

#### .env 設定項目

| 項目 | 値の例 | 説明 | 
|---|---|---|
| BOT_PORT | 8000 | FastAPI がリクエストを受け付けるポート |
| FRONT_PORT | 5173 | デバッグ UI (Vite dev server) の対ホストポート |
| DB_PORT | 5432 | Q&Aおよび埋め込みベクトルデータを保存するPostgreSQL DBコンテナの対ホストポート |
| DB_DIR | db_nomic | DBとして使うディレクトリ。 ./{DB_DIR}/data 下には PostgreSQL のデータクラスタが構築される（永続化ボリューム）。 |
| EMBEDDING_VECTOR_DIM | 768 | `db_hiroba_qa_init` が `question_altered.embedding` を `VECTOR(N)` で作成する際の次元数。`DB_DIR` に対応させる（`db_nomic`→768, `db_multilingual`→384）。埋め込みモデル差異はこの1変数で吸収し、スキーマは単一のマイグレーション履歴で管理する（ADR-0017）。 |
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
docker compose logs -f web_backend        # FastAPI の起動ログ
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
| 質問を送ると `502 Bad Gateway` が返る | `chatbot_app` が起動しているか確認。`docker compose logs web_backend` を参照 |
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
python -m pip install -e web_backend
evaluate
```

- 直接モジュールを実行する方法:

```bash
python -m main.evaluate --top-k 10 --output /tmp/results.csv
```

実行時は `DATABASE_URL`, `LMSTUDIO_EMBEDDING_URL`, `MODEL_EMBEDDING` が環境に設定されている必要があります。出力に MRR が表示され、`--output` でクエリごとの順位情報を CSV に保存できます。

## Knowledge MCP サーバ

`knowledge_mcp/` は、既存の Q&A ナレッジベースを MCP（Model Context Protocol）経由で検索・管理するための独立サービスです（IMPL-202608041013 / ADR-0001〜0006）。既存 `web_backend` の `search_similar` はそのまま残し、並行運用します。

- トランスポート: Streamable HTTP（MCP エンドポイントは `/mcp`、ヘルスチェックは `/health`）
- 提供ツール:
  - `search_knowledge` … クエリの意味検索。`tags` / `category` フィルタ、`min_score` に対応
  - `list_tags` / `create_tag` / `rename_tag` / `move_tag` / `delete_tag` … タグマスタ管理（`tag` / `qa_tag` テーブル）
  - `set_tag_description` / `add_tag_alias` / `remove_tag_alias` … タグの説明文・同義語管理（IMPL-202608060837 / `tag_alias` テーブル）。`create_tag` / `rename_tag` は任意の `description` パラメータに対応。`list_tags` は `description` / `aliases` を含む
  - `list_qa` / `get_qa` / `create_qa` / `update_qa` / `list_categories` … QA管理（IMPL-202608060837 / ADR-0014）。`create_qa` は `question_text` から embedding を計算し、主となる `question_altered`（`is_primary=true`）を1件生成する

### 事前準備（DBスキーマ移行）

`title` 列・`tag` / `qa_tag` テーブル、および `question_altered.is_primary` 列の作成は、`db_hiroba_qa_init` サービスが `docker compose up` 時に自動的に適用します（IMPL-202608061016）。従来の手動 SQL 適用（`docker compose exec ... psql ...`）や `title` 補完バッチの手動実行は不要になりました。旧 `knowledge_mcp/migrations/` の内容は `db_hiroba_qa_init/migrations/` の単一マイグレーション履歴（`0003_add_title_and_tag_tables.sql`, `0004_add_question_altered_is_primary.sql`）へ統合済みです。

> 注: 現行の `data/exportjson_withguid.json` にはレコード単位の `tags` フィールドが無いため、`db_hiroba_qa_init` の補完処理では `title` のみが補完されます（タグ投入は 0 件）。

### 起動

```bash
docker compose up -d knowledge_mcp
# ヘルスチェック
curl -f http://localhost:${KNOWLEDGE_MCP_PORT:-8100}/health
```

`.env` 設定項目（`.env.example` 参照）:

| 項目 | 値の例 | 説明 |
|---|---|---|
| KNOWLEDGE_MCP_PORT | 8100 | Knowledge MCP サーバの対ホストポート |
| KNOWLEDGE_MCP_DEFAULT_TOP_K | 5 | `search_knowledge` の既定 top_k |

> セキュリティ: 本フェーズでは追加認証を実装していません（Open Issue #4, #10）。書き込み系のタグ管理ツールを含むため、社内ネットワーク外へポートを公開しないでください。

## Tag Selector MCP サーバ

`tag_selector_mcp/` は、質問文に最も関連する既存タグを選択するための独立サービスです（IMPL-202608051712 / ADR-0007〜0012）。Knowledge MCP が管理する `tag` テーブルを正本とし、`tag_alias`（同義語）と `tag.description` を用いて選択します。

- トランスポート: Streamable HTTP（MCP エンドポイントは `/mcp`、ヘルスチェックは `/health`）
- タグ選択方式（MVP, ADR-0009）: Alias 辞書によるルールベース照合 ＋ ローカルLLM（LM Studio）による一段階選択。Embedding 層・階層探索は未実装。
- 提供ツール:
  - `select_tags` … 質問文に関連するタグを `id` / `name` / `score` / `path` で score 降順に返す（`max_tags` / `confidence_threshold` に対応）
  - `list_taxonomy` … キャッシュ中のタグ知識ベース（`id` / `name` / `description` / `parent_tag_id` / `aliases`）を返す
  - `reload_taxonomy` … タグ知識ベースをDBから再読込し件数を返す
- タグ知識ベースは起動時ロード＋定期ポーリング（`TAXONOMY_RELOAD_INTERVAL_SEC`）＋ `reload_taxonomy` による明示リロードでメモリにキャッシュします（ADR-0011）。

### 事前準備（DBスキーマ移行・暫定シード）

`tag.description` 列・`tag_alias` テーブルの作成、および動作確認用の暫定 description / alias 投入は、`db_hiroba_qa_init` サービスが `docker compose up` 時に自動的に適用します（IMPL-202608061016）。従来の手動 SQL 適用・暫定シードスクリプトの手動実行は不要になりました。旧 `tag_selector_mcp/migrations/` の内容は `db_hiroba_qa_init/migrations/0005_add_tag_description_and_alias.sql` および `db_hiroba_qa_init` のシード処理へ統合済みです。

> 注: この暫定 description / alias は MVP 動作確認用のデータです。本番運用向けの網羅的な整備は Knowledge MCP 側のタグ管理ツール拡張後に別途行います（Open Issue #2）。

### 起動

LM Studio でチャット補完モデルをロードし、`.env` に接続情報を設定した上で起動します。

```bash
docker compose up -d tag_selector_mcp
# ヘルスチェック
curl -f http://localhost:${TAG_SELECTOR_MCP_PORT:-8200}/health
```

`.env` 設定項目（`.env.example` 参照）:

| 項目 | 値の例 | 説明 |
|---|---|---|
| TAG_SELECTOR_MCP_PORT | 8200 | Tag Selector MCP サーバの対ホストポート |
| LLM_PROVIDER | lmstudio | LLM 実装の切り替え（MVP は `lmstudio` のみ） |
| LMSTUDIO_CHAT_URL | http://host.docker.internal:1234/v1/chat/completions | LM Studio のチャット補完API（ベースURL・フルURLどちらでも可） |
| LMSTUDIO_CHAT_MODEL | （ロード済みモデル名） | チャット補完に使用するモデル名 |
| TAXONOMY_RELOAD_INTERVAL_SEC | 300 | タグ知識ベースの自動リロード間隔（秒） |
| TAG_SELECTOR_DEFAULT_MAX_TAGS | 3 | `select_tags` の既定 `max_tags` |
| TAG_SELECTOR_DEFAULT_CONFIDENCE_THRESHOLD | 0.0 | `select_tags` の既定 `confidence_threshold` |

> セキュリティ: 本フェーズでは追加認証を実装していません（Open Issue #6）。社内ネットワーク外へポートを公開しないでください。


## QA・タグ管理 UI（front_dev / web_backend 拡張）

`front_dev` の `/admin` 配下に、QAデータとタグ階層を登録・編集するための管理画面を追加しました（IMPL-202608060837 / ADR-0013〜0015）。`web_backend` が MCP クライアントとして Knowledge MCP のツールを呼び出す BFF（`/api/*`）を提供し、`chatbot_db` への直接書き込みは行いません。

- 画面（`react-router-dom` を `/admin` 配下のみで使用。既存3画面の分岐方式は不変）:
  - `http://localhost:5173/admin/qa` … QA一覧（キーワード・カテゴリ・タグで絞り込み、ページング）
  - `http://localhost:5173/admin/qa/new` … QA新規登録
  - `http://localhost:5173/admin/qa/:id` … QA編集
  - `http://localhost:5173/admin/tags` … タグ階層（作成・名称変更・説明編集・親変更・削除。同義語は表示のみ）
- BFF API（`web_backend`、`/api` プロキシ経由）:
  - `GET/POST /api/qa`, `GET/PUT /api/qa/{id}`, `GET /api/categories`
  - `GET/POST /api/tags`, `PUT/DELETE /api/tags/{id}`
- タグ削除は、`qa_tag` 参照・子タグ存在時は拒否され、削除可能な場合は紐づく `tag_alias` も連動削除されます。

### 事前準備

Knowledge MCP サーバ（上記）が起動していることが前提です。`question_altered.is_primary` 列を含むスキーマ移行は `db_hiroba_qa_init` が自動適用します（IMPL-202608061016）。`web_backend` は `KNOWLEDGE_MCP_URL` で Knowledge MCP へ接続します。

`.env` 設定項目（`.env.example` 参照）:

| 項目 | 値の例 | 説明 |
|---|---|---|
| KNOWLEDGE_MCP_URL | http://knowledge_mcp:8100/mcp | `web_backend` が接続する Knowledge MCP のエンドポイント |

### 起動

```bash
docker compose up -d knowledge_mcp web_backend frontend
```

ブラウザで `http://localhost:5173/admin/qa` を開きます。`web_backend` は `knowledge_mcp` のヘルスチェック完了後に起動します（`depends_on`）。

> セキュリティ: 本フェーズでは書き込み系API（QA・タグの登録編集削除）に追加認証を実装していません（Open Issue #2）。社内ネットワーク外へ公開しないでください。
