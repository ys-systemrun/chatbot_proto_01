# 実装指示書: db_hiroba_qa_init（DBマイグレーション・シード専用サービスの分離）

- 文書番号: IMPL-202608061016
- 対象プロジェクト: chatbot_invitro
- 根拠文書: `docs/requirement/202608061016.md`（要件定義書）, `docs/adr/0016-db-hiroba-qa-init-service-separation.md`, `docs/adr/0017-db-hiroba-qa-init-migration-tool-selection.md`, `docs/adr/0018-db-hiroba-qa-init-seed-idempotency-and-startup-order.md`
- 対象コンポーネント: `db_hiroba_qa_init`（新規）, `db_hiroba_qa`（既存, 責務縮小）, `web_backend`（既存, シード関連コード撤去）, `knowledge_mcp`（既存, `migrations/` 撤去）, `tag_selector_mcp`（既存, `migrations/` 撤去）, `docker-compose.yml`, `.env.example`, `README.md`
- 前提: 本書はREQ-202608061016・ADR-0016〜0018の決定事項をコード変更に落とし込むための作業指示である。要件・設計判断自体の変更が必要になった場合は、実装より先に上記文書を更新すること。

## 1. 変更の概要

現行、スキーマ作成は `db_hiroba_qa` の `init.sql`（初回起動時のみ実行）で、シードは `web_backend` の `seed` 系console-scriptの手動実行で、追加のスキーマ変更は `knowledge_mcp/migrations/`・`tag_selector_mcp/migrations/` の手動SQL適用で、それぞれ個別に行われている。本実装では、これらすべてを新設の `db_hiroba_qa_init` サービス（ワンショットコンテナ）に集約し、`docker compose up` だけでスキーマ作成とシードが自動完了する状態にする。

## 2. 新規ディレクトリ構成（想定）

```
db_hiroba_qa_init/
  Dockerfile
  pyproject.toml
  migrations/
    0001_initial_schema.sql            # qa_original, category, CREATE EXTENSION vector 等（モデル非依存部分）
    0002_question_altered_table.py     # Pythonステップ: EMBEDDING_VECTOR_DIM を読み込み VECTOR(N) で作成
    0003_add_title_and_tag_tables.sql  # knowledge_mcp/migrations/0001 相当を統合
    0004_add_question_altered_is_primary.sql  # knowledge_mcp/migrations/0002 相当を統合
    0005_add_tag_description_and_alias.sql    # tag_selector_mcp/migrations/0001 相当を統合
  src/
    main.py                # migrate() → seed_if_empty() を順に実行するエントリポイント
    seed_helpers.py         # web_backend/src/seed_helpers.py から移管
    embedding.py            # web_backend/src/embedding.py の seed 用呼び出し部分を移管
    db.py                   # exists_* / insert_* を web_backend/src/db.py から移管
    backfill_title_and_tags.py     # knowledge_mcp/migrations/backfill_title_and_tags.py から移管
    seed_description_and_aliases.py # tag_selector_mcp/migrations/seed_description_and_aliases.py から移管
```

上記のファイル名・分割は実装時の目安であり、レビューの過程で変更してよい。重要なのは「単一のマイグレーション履歴」「migrate→seedの順で1回だけ実行して終了するエントリポイント」という構造を守ることである（ADR-0016, ADR-0017）。

## 3. 作業手順

### 3.1 マイグレーション基盤の構築

1. `db_hiroba_qa_init/` に Python プロジェクトを新設し、`yoyo-migrations` を依存に追加する（ADR-0017）。
2. `db_nomic/init.sql` の内容（`CREATE EXTENSION vector`, `qa_original`, `category`, `tag`, `qa_tag`, `tag_alias` とインデックス）を、モデル非依存のマイグレーションステップ（`.sql`）へ移す。`db_multilingual/init.sql` は `title`/`tag`/`qa_tag`/`tag_alias`/`is_primary` が欠落しているため、**`db_nomic/init.sql` を正本として統合する**（要件定義書2.1節のドリフトを踏まえた判断）。
3. `question_altered` テーブルの作成は、環境変数 `EMBEDDING_VECTOR_DIM`（新設）を読み込み `VECTOR(N)` を組み立てるPythonステップとして実装する（ADR-0017）。`.env.example` に `EMBEDDING_VECTOR_DIM` を追加し、`DB_DIR=db_nomic` のときは `768`、`DB_DIR=db_multilingual` のときは `384` を設定する例を記載する。
4. `knowledge_mcp/migrations/0001_add_title_and_tag_tables.sql`・`0002_add_question_altered_is_primary.sql`・`tag_selector_mcp/migrations/0001_add_tag_description_and_alias.sql` の内容を、上記マイグレーション履歴に後続ステップとして統合する。統合後、`knowledge_mcp/migrations/`・`tag_selector_mcp/migrations/` から該当ファイルを削除する。
5. 既存の全SQLに `IF NOT EXISTS` / `IF NOT EXISTS` 相当のガードが付いていることを確認する（既存ファイルは概ね対応済み。移植時に欠けている箇所がないか確認する）。

### 3.2 シード処理の移管

1. `web_backend/main/seed.py`・`web_backend/src/seed_helpers.py` の内容を `db_hiroba_qa_init/src/` へ移す。
2. `web_backend/src/db.py` の `exists_category` / `exists_qa_original` / `exists_question_altered` / `insert_category` / `insert_qa_original` / `insert_question_altered` を `db_hiroba_qa_init/src/db.py` へ移す。**`search_similar` はチャット機能で使用するため `web_backend/src/db.py` に残す**（10章、要件定義書10章と同一方針）。
3. `web_backend/src/embedding.py` の `get_embedding` はチャット機能（`/ask` のクエリembedding計算）でも使うため、`web_backend` 側にも残す。`db_hiroba_qa_init` 側には、シード専用の呼び出しコードとして同等の関数を配置する（コードの共有方法は、共通パッケージ化するか単純に複製するかは実装時の判断でよい。要件定義書のスコープはロジックの複製・移管方針までを定めるものであり、共有方法自体は本書でも指定しない）。
4. `knowledge_mcp/migrations/backfill_title_and_tags.py`・`tag_selector_mcp/migrations/seed_description_and_aliases.py` の内容を、`db_hiroba_qa_init` のシードフローに追加ステップとして統合する（3.3節参照）。
5. `main_seed_all` 相当の実行順序（`category` → `qa_original` → `question_altered` → title/tags backfill → tag description/alias seed）をエントリポイントで定義する。既存の存在チェックによる冪等性（ADR-0018）を維持する。

### 3.3 エントリポイントの実装

`db_hiroba_qa_init/src/main.py`（想定）に、以下の処理順序を実装する。

1. マイグレーション適用（3.1節、yoyo-migrationsの `apply_migrations` 相当のAPI呼び出し）。
2. `category` の存在チェック→未投入なら投入。
3. `qa_original` の存在チェック→未投入なら投入。
4. `question_altered` の存在チェック→未投入なら、行ごとに embedding 計算のうえ投入。
5. `title` 補完バックフィル（`backfill_title_and_tags.py` 相当。既存レコードに対する冪等な補完処理のため、存在チェックではなく「未設定の行のみ」を対象にする既存ロジックをそのまま踏襲する）。
6. `tag.description` / `tag_alias` の暫定シード（`seed_description_and_aliases.py` 相当。同様に冪等）。
7. いずれかの手順で例外が発生した場合、ログに出力の上、非0の終了コードでプロセスを終了する（ADR-0018）。全手順が成功した場合は終了コード0で終了する。

### 3.4 Dockerfile

`web_backend/Dockerfile` を参考に、Python環境を構築し、`CMD` はサーバー起動コマンド（`fastapi dev` 等）ではなく `src/main.py` を1回実行して終了するコマンドとする。

### 3.5 web_backend からの撤去

1. `web_backend/pyproject.toml` の `[project.scripts]` から `seed` / `seed_category` / `seed_qa_original` / `seed_question_altered` を削除する。
2. `web_backend/main/seed.py` を削除する（3.2節で移管済み）。
3. `web_backend/src/seed_helpers.py` を削除する（3.2節で移管済み）。
4. `web_backend/src/db.py` から `exists_*` / `insert_*` を削除し、`search_similar` のみ残す（3.2節）。
5. README「利用前に」節の手順3（シーディングの手動実行に関する記載）を、「`docker compose up` 時に `db_hiroba_qa_init` が自動的に完了させる」旨に更新する。

### 3.6 knowledge_mcp / tag_selector_mcp からの撤去

1. `knowledge_mcp/migrations/` ディレクトリを削除する（3.1節・3.2節で統合済み）。
2. `tag_selector_mcp/migrations/` ディレクトリを削除する（同上）。
3. README「Knowledge MCP サーバ」「Tag Selector MCP サーバ」の各「事前準備（DBスキーマ移行）」節を削除し、「`db_hiroba_qa_init` が自動的に適用する」旨の記載に置き換える。

### 3.7 docker-compose.yml の変更

1. `db_hiroba_qa` サービスから `- ./${DB_DIR:-db_nomic}/init.sql:/docker-entrypoint-initdb.d/init.sql` の行を削除する（データボリュームのマウント行は残す）。
2. 新規サービス `db_hiroba_qa_init` を追加する。

```yaml
  db_hiroba_qa_init:
    build: ./db_hiroba_qa_init
    container_name: chatbot_db_init
    environment:
      - DATABASE_URL=postgresql://postgres:postgres@db_hiroba_qa:5432/chatbot
      - EMBEDDING_VECTOR_DIM=${EMBEDDING_VECTOR_DIM}
      - CSV_DATA_DIR=${CSV_DATA_DIR}
      - QA_ORIGINAL_FILE=${QA_ORIGINAL_FILE}
      - QUESTION_ALTERED_FILE=${QUESTION_ALTERED_FILE}
      - CATEGORY_FILE=${CATEGORY_FILE}
      - LMSTUDIO_EMBEDDING_URL=${LMSTUDIO_EMBEDDING_URL}
      - MODEL_EMBEDDING=${MODEL_EMBEDDING}
    volumes:
      - ./${CSV_DATA_DIR:-data}:/data
    depends_on:
      db_hiroba_qa:
        condition: service_healthy
    restart: "no"
```

3. `web_backend` / `knowledge_mcp` / `tag_selector_mcp` の `depends_on` に、`db_hiroba_qa_init: condition: service_completed_successfully` を追加する（既存の `db_hiroba_qa: condition: service_healthy` は残してよい。両条件を満たしてから起動される）。

```yaml
    depends_on:
      db_hiroba_qa:
        condition: service_healthy
      db_hiroba_qa_init:
        condition: service_completed_successfully
      # 既存の他サービスへの depends_on はそのまま維持
```

4. 上記の `depends_on` に `condition: service_completed_successfully` を使うため、実装着手前に開発者・CI環境の Docker Compose バージョンが対応しているか確認する（要件定義書 Open Issue #3）。対応していない場合は本書を更新し、代替の待機処理方式を指示し直す。

### 3.8 .env.example の変更

1. `EMBEDDING_VECTOR_DIM` を追加し、`DB_DIR` の値との対応関係をコメントで明記する（例: `db_nomic` なら `768`、`db_multilingual` なら `384`）。
2. `CSV_DATA_DIR` / `QA_ORIGINAL_FILE` / `QUESTION_ALTERED_FILE` / `CATEGORY_FILE` は `db_hiroba_qa_init` でも使用するため変更不要（既存のまま両サービスで共有する）。

## 4. 既存環境（適用済みボリューム）への移行

要件定義書 Open Issue #2 に対応する暫定手順。詳細は実装時にADR追記または別ADRとして確定してよい。

1. 既に手動migration・シードが完了しているローカル環境（`db_nomic/data` 等）に対しては、yoyo-migrationsの追跡テーブルに、統合したマイグレーション（3.1節の1〜5の各ステップ）を「適用済み」として登録するベースライン化コマンドを用意する（yoyo-migrationsの `mark` コマンド相当）。
2. 上記ベースライン化を行わずに `db_hiroba_qa_init` を実行した場合、既に存在するテーブル・列に対して `CREATE TABLE IF NOT EXISTS` 等が無害に完了することを想定しているが、`ALTER TABLE ... ADD COLUMN` 系の一部が `IF NOT EXISTS` 未対応であれば実行時エラーになる可能性がある。実装時に全マイグレーションSQLの再実行安全性を確認すること。

## 5. テスト・確認観点

- [ ] 新規環境（`db_nomic/data` を空にした状態）で `docker compose up` を実行し、`db_hiroba_qa_init` のログでマイグレーション・シードが順に実行され、正常終了することを確認する。
- [ ] 直後に `db_hiroba_qa_init` を再実行（`docker compose up db_hiroba_qa_init` の再作成等）し、重複投入エラーが発生しないことを確認する。
- [ ] `web_backend` / `knowledge_mcp` / `tag_selector_mcp` が `db_hiroba_qa_init` の完了前に起動しないことを確認する（`docker compose up` 実行直後に `docker compose ps` でステータス遷移を確認する）。
- [ ] `LMSTUDIO_EMBEDDING_URL` を意図的に無効な値にしてシードを失敗させ、`db_hiroba_qa_init` が非0で終了し、他サービスが起動しないことを確認する。
- [ ] `.env` の `DB_DIR` / `EMBEDDING_VECTOR_DIM` を `db_multilingual` / `384` に切り替えて起動し、`question_altered.embedding` が `VECTOR(384)` で作成され、`title`/`tag`/`qa_tag`/`tag_alias`/`is_primary` も含めて `db_nomic` と同一のスキーマになっていることを確認する（既存ドリフトの解消確認）。
- [ ] 既存チャット機能（`/ask` 等）・Knowledge MCP・Tag Selector MCPの既存機能が、本変更後も変更前と同様に動作することを確認する（回帰確認）。

## 6. ロールバック方針

- `db_hiroba_qa_init` の導入に伴う変更は `docker-compose.yml` の `depends_on` 変更・サービス追加が中心であり、問題が発生した場合は当該サービス定義を削除し、`web_backend` 側に一時的に手動シードスクリプトを復元することで旧構成に戻せる（Gitでの変更取り消しを前提とする）。
- データベースのスキーマ自体は追加のみ（列追加・テーブル追加）であり、ロールバック時にデータを破壊する変更は行わない。

## 7. Open Issues（実装時に確定が必要な事項、要件定義書13章と同一）

要件定義書 `docs/requirement/202608061016.md` 13章のOpen Issues（embeddingプロバイダ抽象化、既存環境との整合、Compose バージョン要件、マイグレーション実行ユーザーの権限、embeddingエンドポイントの起動待ち、サービス名称の確定）は、実装着手前に一度確認し、方針が変わった場合は本書および要件定義書・ADRを更新すること。
