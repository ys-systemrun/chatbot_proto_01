# ADR-0016: db_hiroba_qa_init サービスの分離（マイグレーション・シード責務の集約）

- ステータス: Accepted
- 日付: 2026-08-06
- 関連: `docs/requirement/202608061016.md`

## コンテキスト

現行、スキーマ作成は `db_hiroba_qa`（PostgreSQL + pgvector）の `docker-entrypoint-initdb.d` に配置した `init.sql`（データディレクトリが空の初回起動時のみ実行）で行い、以後のスキーマ変更は `knowledge_mcp/migrations/` や `tag_selector_mcp/migrations/` の一回限りのSQLファイルを運用者が `docker compose exec ... psql ...` で手動適用している。初期データ投入（シード）は `web_backend` の `seed` 系console-scriptを運用者が手動実行するものであり、いずれも「コンテナを作れば即利用できる」状態を提供できていない。

スキーマ作成責務が `db_hiroba_qa`（DB本体イメージ）に、シード責務が `web_backend`（アプリケーションイメージ）に、部分的な追加スキーマ変更が `knowledge_mcp` / `tag_selector_mcp` の各migrationsディレクトリに分散しており、いずれのサービスも「自分の本来の責務（チャットAPI提供、QA/タグ管理ツール提供等）」とは別に、DB初期化の責務を部分的に抱えている状態である。

## 決定

スキーマ作成（マイグレーション）と初期データ投入（シード、embedding計算を含む）の責務を、`db_hiroba_qa` および `web_backend` から切り出し、`db_hiroba_qa_init` という専用の一時的（ワンショット）サービスに集約する。

- `db_hiroba_qa_init` は `db_hiroba_qa` が `service_healthy` になった後に起動し、①マイグレーション実行 → ②未投入テーブルへのシード実行、の順に処理を行い、完了後は正常終了（exit code 0）する。常駐プロセスは持たない。
- `db_hiroba_qa` は PostgreSQLの起動・データ永続化のみの責務に縮小し、`init.sql` のマウントは廃止する。
- `web_backend` は `seed` 系console-script・`main/seed.py`・`src/seed_helpers.py` を撤去し、チャットAPI提供のみの責務に戻す。
- `knowledge_mcp` / `tag_selector_mcp` の `migrations/` 配下（手動適用SQL・バックフィル/暫定シードスクリプト）は `db_hiroba_qa_init` のマイグレーション履歴・シード処理へ統合する。
- `web_backend` / `knowledge_mcp` / `tag_selector_mcp` は、`db_hiroba_qa_init` が `service_completed_successfully` となった後に起動する（`depends_on` に追加。ADR-0018で詳細を定める）。

## 検討した代替案

- **現状維持（`init.sql` ＋ 手動migration運用の継続）**: 追加のサービス・実装コストが発生しない一方、2.1節（要件定義書）で確認した `db_nomic`/`db_multilingual` の `init.sql` ドリフトのような不整合が今後も発生し続けるリスクを許容することになる。運用者依存の手動手順である点も解消されないため、見送った。
- **`web_backend` の起動時（アプリケーション起動前）にマイグレーション・シードを組み込む方式**: 専用サービスを新設せず、`web_backend` のエントリポイントで migrate→seed→`fastapi dev` 起動、という順序を実装する案。専用サービスを増やさない利点はあるが、①`knowledge_mcp` / `tag_selector_mcp` も同じDBを参照するため、どのサービスが「DB初期化の責任者」かが曖昧になる、②`web_backend` の起動失敗（アプリ側の理由）とDB初期化失敗の区別がしにくい、③複数サービスが同時に起動する場合の初期化処理の競合（同時に複数コンテナがmigrateを試みる）を避ける工夫が別途必要になる、という理由から見送った。専用のワンショットサービスに一本化することで、DB初期化の責任者を単一化し、他サービスは「初期化済みDBに接続するだけ」という単純な前提を置ける。
- **`db_hiroba_qa`（DBイメージ自体）にマイグレーション・シードのエントリポイントを組み込む方式**: DBコンテナ起動スクリプト内でマイグレーション・シードも実行する案。PostgreSQL公式イメージの起動プロセスに独自ロジックを混在させることになり、DBイメージのアップデート（pgvectorイメージのバージョン追従等）とアプリケーション側のマイグレーション/シードロジックのバージョン管理が結合してしまうため見送った。

## 結果・影響

- DB初期化（スキーマ作成・シード）の責任者が `db_hiroba_qa_init` に一本化され、`web_backend` / `knowledge_mcp` / `tag_selector_mcp` は「初期化済みのDBに接続する」という前提のみを持てばよくなる。
- `docker-compose.yml` の変更（`db_hiroba_qa_init` サービス追加、`db_hiroba_qa` の `init.sql` マウント削除、各アプリケーションサービスの `depends_on` 変更）が必要になる。
- `web_backend` の `pyproject.toml` から `seed` 系console-scriptsが撤去されるため、README「利用前に」節の手順（手動シード実行の説明）を更新する必要がある（要件定義書10章）。
- `knowledge_mcp` / `tag_selector_mcp` の README「事前準備（DBスキーマ移行）」節の手動適用手順が不要になる。
- 既にシード済み・手動migration適用済みの開発環境への移行方法は別途整理が必要（要件定義書 Open Issue #2、ADR-0017参照）。
