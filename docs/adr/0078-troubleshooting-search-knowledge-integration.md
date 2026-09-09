# ADR-0078: トラブルシューティング記事のsearch_knowledge統合方式

- ステータス: Accepted
- 日付: 2026-09-07
- 関連: `docs/requirement/202609071337_トラブルシューティング情報源追加要件定義書.md`, ADR-0058, ADR-0059, ADR-0076

## コンテキスト

発注者は、トラブルシューティング記事（ADR-0076で新設する`troubleshooting_article`）を、チャットボットが質問に回答する際の検索対象（RAG検索、`knowledge_mcp`の`search_knowledge`ツール）に含めたいとの意向を示した。

調査の結果、既存の`knowledge_mcp`は複数情報源の追加を既に見込んだ抽象化を持っていることが判明した。`Document`モデル（`models/document.py`）は`source_type`フィールドを持ち現状`"qa"`固定だが複数種別を想定した設計であり、`SearchService`（`services/search_service.py`）は複数の`Repository`を受け取り結果を統合する設計で、docstringに「MVPではQARepositoryのみが渡される想定だが、将来のPDF/Manual追加を見据え、複数repositoryを渡しても動作するよう実装する」と明記されている。`QARepository.search()`は祖先タグ展開（ADR-0058）とタグ構成類似度・埋め込み類似度の重み付き合成スコアリング（ADR-0059）を実装済みである。

一方、トラブルシューティング記事には`hiroba_question_altered`（言い換え質問文）に相当する自然な元データが存在しない（HTML原本は現象・原因・案内内容を記述した静的なリファレンス文書であり、ユーザー発話の言い換えバリエーションを持たない）。発注者に、記事ごとに単一embeddingとするか、言い換え質問文相当の別テーブルを新設するかを確認したところ、記事ごとの単一embedding方式を選択した。

## 決定

**`knowledge_mcp`に新規`TroubleshootingRepository`を追加し、既存の`Repository`インターフェースを実装した上で`SearchService`へ登録することでマルチソース検索を実現する。埋め込みは記事単位の単一embedding方式とし、`hiroba_question_altered`のような言い換えバリエーション用の別テーブルは新設しない。**

1. **新規Repositoryの追加のみで統合**: `repository/troubleshooting_repository.py`に`TroubleshootingRepository`を新設し、`SOURCE_TYPE = "troubleshooting"`とする。`SearchService`自体は変更不要であり、DIで渡すrepositoryのリストに追加するだけで統合が完了する。これは`SearchService`のdocstringが明記していた将来の拡張シナリオそのものである。
2. **既存スコアリングロジックの踏襲**: `troubleshooting_article.embedding <=> query_vec`による埋め込み距離スコアに加え、`QARepository`と同一の祖先タグ展開（`tag`の再帰CTE）・タグ構成類似度（Jaccard係数）との重み付き合成を適用する。重み（`TAG_SIMILARITY_WEIGHT`）は既存のQA検索と共用の環境変数とし、情報源によってスコアリング方針が乖離しないようにする。
3. **記事単位の単一embedding方式**: 言い換え質問文相当の別テーブルは新設せず、`troubleshooting_article`テーブル自体に`embedding`列を持たせる。埋め込み元テキストは`title + subtitle + symptom + cause + guidance`の結合を既定とする。対象記事数が現時点で65件程度と小規模であり、静的なリファレンス文書という性質上、言い換えバリエーションの網羅よりもまず単一の代表テキストでの検索精度を検証し、不足があれば言い換えテーブルの追加を将来検討する段階的アプローチをとる。
4. **`Document`への反映**: `TroubleshootingRepository`は`Document(id, source_type="troubleshooting", title, content=guidance, score, metadata={"tags": [...], "category": None, "source_key": ...})`を返す。`SearchService`は既存のQA由来`Document`と合わせてscore降順にソートし、`search_knowledge`は情報源を問わず統合済みの結果配列を返す。

## 検討した代替案

- **`hiroba_question_altered`と同様の言い換え質問文テーブル（例:`troubleshooting_article_altered`）を新設し、記事ごとに複数の想定ユーザー発話を人手またはLLM生成で用意してembeddingする**: 検索精度（多様な言い換えへの頑健性）は記事単位の単一embeddingより高まる可能性がある。しかし、言い換え文の用意（人手作成またはLLM生成＋レビュー）という初期データ作成コストが新たに発生し、対象記事数が小規模な現段階では投資対効果が見合わない。発注者は記事単位の単一embedding方式を選択し、将来の精度検証結果次第で本代替案を再検討する余地を残した（要件定義書 Open Issue #2 参照）。

- **`search_knowledge`のSQLクエリ自体を`UNION ALL`で拡張し、単一のクエリで両データソースを横断検索する**: repositoryを1つ追加する方式に比べてDBラウンドトリップが1回で済む可能性がある。しかし`QARepository`の既存クエリは`hiroba_question_altered`と`hiroba_qa_original`の結合を前提にした構造であり、`troubleshooting_article`（単一テーブルで完結し中間の言い換えテーブルを持たない）と構造が異なるため、`UNION ALL`化は既存クエリの大幅な書き換えを要し、`Document`/`Repository`/`SearchService`という既存の抽象化層を無視することになる。既存アーキテクチャが既に想定していた「repository追加による統合」の方が変更範囲が小さく保守性も高いため不採用とした。

- **専用の別MCPツール（例:`search_troubleshooting`）を新設し、`agent_invitro`側で`search_knowledge`と並行して呼び出す**: `knowledge_mcp`側の変更を最小化できる。しかし`agent_invitro`側の呼び出しロジック・結果マージ・タグ継続判定（ADR-0057・ADR-0062）に手を入れる必要が生じ、影響範囲がより大きくなる。既存の`SearchService`によるサーバ側統合の方が、呼び出し側（`agent_invitro`）に変更を要求しない点で優れるため不採用とした。

## 結果・影響

- `knowledge_mcp`に新規ファイル`repository/troubleshooting_repository.py`が追加される。`repository/qa_repository.py`との間でスコアリングヘルパー（`distance_to_score`/`_jaccard`等）の重複が生じるため、実装フェーズで共通モジュールへの切り出しを検討する。
- `search_knowledge`ツールの外部契約（引数・戻り値スキーマ）は変更されない。`agent_invitro`側の呼び出しコードは変更不要と想定される（実装フェーズで動作確認する）。
- `troubleshooting_article.embedding`の次元数は`hiroba_question_altered.embedding`と同一次元に揃える（同一の埋め込みモデル・`embed_fn`を使い回すため）。
- 記事編集時のembedding再計算タイミング（保存時同期・非同期・手動トリガー）は詳細設計フェーズで確定する（要件定義書 Open Issue #2）。
- 将来、検索精度が不足する場合は代替案1（言い換えテーブルの追加）を再検討する。
