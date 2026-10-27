# knowledge_mcp/src/knowledge_mcp/models — データモデル

リポジトリと MCP ツールの間でやり取りするデータクラスと、業務エラーの例外クラスです。各クラスは MCP 出力用の `to_dict()` を持ちます。

## 構成

| 名前 | 説明 |
|---|---|
| [`__init__.py`](__init__.py) | パッケージ宣言（空）。 |
| [`document.py`](document.py) | `Document`。`search_knowledge` の検索結果 1 件（id・source_type〔`qa` / `troubleshooting`〕・title・content・score・metadata）。`QARepository` / `TroubleshootingRepository` が返す。 |
| [`qa.py`](qa.py) | QA 管理用の `QaSummary`（一覧行）・`QaDetail`（詳細）と業務エラー `QaError`（ADR-0014）。`QaManagementRepository` が使う。 |
| [`question_altered.py`](question_altered.py) | 言い換え質問文（`is_primary=false` の行）1 件を表す `QuestionAltered` と業務エラー `QuestionAlteredError`（ADR-0064）。`QuestionAlteredRepository` が使う。 |
| [`tag.py`](tag.py) | `TagNode`。タグ階層の 1 ノード（親タグ・説明・同義語・タグフォルダ〔ADR-0072〕・表示順〔ADR-0074〕・子ノード）。`TagRepository` が使う。 |
| [`troubleshooting.py`](troubleshooting.py) | トラブルシューティング記事管理用の `TroubleshootingSummary`（一覧行）・`TroubleshootingDetail`（詳細）と業務エラー `TroubleshootingError`（ADR-0079）。`TroubleshootingManagementRepository` が使う。 |
