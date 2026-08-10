# ADR-0003: ベクトルストア方針（既存 pgvector を継続利用）

- ステータス: Accepted
- 日付: 2026-08-04
- 関連: `docs/requirement/202608041002.md`

## コンテキスト

参照資料（`docs/requirement/202608040945.md`）では、専用ベクトルDB（FAISS / Chroma / Qdrant 等）を新規導入する案が例示されていた。一方、chatbot_invitro には既に pgvector 拡張済みの PostgreSQL（`chatbot_db`）があり、`qa_original` / `question_altered`（embedding VECTOR(768)）にQAデータの埋め込みが投入済みで、既存 `DB.search_similar` によるベクトル距離検索が稼働している。

## 決定

MVPにおいて、Knowledge MCP サーバの QARepository は **既存 chatbot_db（pgvector）を読み取り専用で再利用する**。新規ベクトルDBミドルウェアは導入しない。

## 検討した代替案

- **専用ベクトルDB（Chroma / Qdrant / FAISS等）の新規導入**: ハイブリッド検索（ベクトル＋BM25）や大規模データでのスケーラビリティに有利な場合があるが、現時点のデータ規模・要件では過剰投資と判断し見送った。将来、PDF/マニュアル等、性質の異なるデータソースを追加する際に改めて要否を検討する。

## 結果・影響

- 追加のミドルウェア導入・運用コストが発生せず、既存の投入済み embedding データをそのまま利用できる。
- 既存 `search_similar` のSQL（`question_altered` ⋈ `qa_original`、`embedding <=>` によるソート）をベースに QARepository を設計できる。
- **既存スキーマには `title` および `tags` に相当するカラムが存在しないため、共通 Document モデルが要求する metadata（タイトル・タグ）を満たすにはスキーマ拡張（マイグレーション）が必須となる**（要件定義書 7.3節）。これは本ADRを採用したことによる直接的な追加コストである。tagsの具体的なスキーマ表現（関連テーブル化）は ADR-0005 で別途定める。
- 既存 FastAPI app と検索用DBを共有するため、将来的な負荷増大時にはDB接続プールやリソース競合を考慮する必要がある。
- 将来、PDFや全文検索が必要なデータソースを追加する際、pgvectorのみで全ての検索要件（全文検索・ハイブリッド検索等）を満たせるかは再評価が必要（Open Issue）。
