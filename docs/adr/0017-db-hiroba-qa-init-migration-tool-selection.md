# ADR-0017: マイグレーションツールの選定と embedding モデル別スキーマ差異への対応方針

- ステータス: Accepted
- 日付: 2026-08-06
- 関連: `docs/requirement/202608061016.md`, ADR-0016

## コンテキスト

`db_hiroba_qa_init`（ADR-0016）は、「何らかのマイグレーションツール・ライブラリ」で `CREATE TABLE` 等のスキーマ作成・変更を行うことが要件である。現行、この用途に使えるツール・ライブラリは導入されておらず、`web_backend` / `knowledge_mcp` / `tag_selector_mcp` はいずれもORM（SQLAlchemy等）を使わず、`psycopg2` による生SQLでDB操作を行う構成である。

また、`question_altered.embedding` の次元数（`VECTOR(N)`）は使用する embedding モデルにより異なり（`db_nomic`: 768次元, `db_multilingual`: 384次元）、現行はモデルごとに独立した `init.sql` を用意することで対応している。この方式は、要件定義書2.1節で確認した通り、モデル間でスキーマ内容が既にドリフト（`db_multilingual/init.sql` に `title`/`tag`/`qa_tag`/`tag_alias`/`is_primary` が未反映）している実例を生んでいる。

## 決定

マイグレーションツールとして **yoyo-migrations**（Python製、軽量、SQL/Pythonステップ形式、DB内に適用履歴テーブルを自動作成）を採用する。

embedding モデル別のスキーマ差異（`VECTOR(N)` の次元数）については、**モデルごとに独立したマイグレーション履歴を持つのではなく、単一のマイグレーション履歴の中で次元数のみを環境変数（例: `EMBEDDING_VECTOR_DIM`）でパラメータ化する**方式を採用する。次元に依存するステップ（`question_altered` テーブル作成・列追加）はPythonステップとして実装し、環境変数から次元数を読み込んでSQLを組み立てる。それ以外のモデル非依存なスキーマ（`qa_original`, `category`, `tag`, `qa_tag`, `tag_alias` 等）は、モデルによらず同一のマイグレーション履歴で管理する。

既存の `knowledge_mcp/migrations/*.sql`、`tag_selector_mcp/migrations/*.sql` は、この単一履歴に統合する（要件定義書4.1節）。

## 検討した代替案

- **Alembic**: Pythonエコシステムで広く使われるマイグレーションツールだが、SQLAlchemyのモデル定義と組み合わせて使う（Autogenerate等）ことを前提とした機能が中心であり、本プロジェクトはSQLAlchemy／ORMを一切採用していない。生SQL中心の運用では機能を活かせず、新たにSQLAlchemy依存を持ち込む理由も現時点でないため見送った。将来、ORMを採用する判断がなされた場合は再検討の余地がある。
- **dbmate / golang-migrate**: 言語不問（Goバイナリ）で `.sql` ファイル＋`schema_migrations` テーブルによる管理を行う、実績のあるツール。Pythonへの依存がない利点はあるが、本プロジェクトの他サービス（`web_backend` / `knowledge_mcp` / `tag_selector_mcp`）はいずれもPython/pipベースであり、`db_hiroba_qa_init` にのみ非Python・非pipのツールチェーンを持ち込むことになる。また、embedding次元のパラメータ化（本ADRの決定事項）をSQLファイルのテンプレート化（環境変数展開）で実現する必要があり、Pythonステップで直接組み立てられる yoyo-migrations より実装が煩雑になると判断し見送った。
- **独自の簡易マイグレーションランナー（SQLファイル＋自作の適用履歴テーブル管理スクリプト）**: 現行の `knowledge_mcp/migrations/` 運用の延長にあたる。要件（「何らかのmigrationツール・ライブラリ」）が既存の実績あるライブラリの採用を想定していると考えられること、また適用順序制御・トランザクション制御・ロールバック等を自前で実装・保守するコストを避けるため見送った。
- **モデルごとに独立したマイグレーション履歴を持つ（現行 `init.sql` 方式の延長）**: `db_nomic` 用・`db_multilingual` 用に別々のマイグレーションディレクトリを持ち、モデル非依存のスキーマ変更を両方に反映する運用。現行方式で既に発生しているドリフト（同じ変更を複数箇所に反映し忘れるリスク）がマイグレーション化後も残るため見送った。単一履歴＋次元数パラメータ化により、モデル非依存の変更は自動的に両モデルに適用され、ドリフトの発生源を構造的に排除できる。

## 結果・影響

- `db_hiroba_qa_init` に yoyo-migrations への依存が追加される。
- `question_altered` のスキーマ定義を含むマイグレーションステップはPythonステップとして実装する必要があり、それ以外は `.sql` ファイルで記述できる。
- 単一履歴化により、`db_nomic` / `db_multilingual` いずれの `DB_DIR` で起動した場合も、`title` / `tag` / `qa_tag` / `tag_alias` / `is_primary` を含む同一のスキーマ（`VECTOR(N)` の次元数のみ異なる）が作成されることが保証される。既存の `db_multilingual/init.sql` のドリフトは、このマイグレーション統合により解消される。
- 既存の `knowledge_mcp/migrations/`・`tag_selector_mcp/migrations/` を単一履歴へ統合する作業（順序の並べ替え、内容の重複排除）が実装フェーズで必要になる。
- 既にこれらの手動SQLを適用済みの開発環境に対し、yoyo-migrations導入後にどう整合を取るか（適用済みとして扱うベースライン化の手順等）は、要件定義書 Open Issue #2 として別途検討が必要。
- 将来、`web_backend` 等でORM（SQLAlchemy）採用の判断がなされた場合、Alembicへの移行を再検討する余地を残す。
