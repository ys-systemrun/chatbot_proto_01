# ADR-0077: 実DB名の再改名（`db_hiroba_qa`→`db_chatbot_knowledge_base`）とタグマスタの中立名称化

- ステータス: Accepted
- 日付: 2026-09-07
- 関連: `docs/requirement/202609071337_トラブルシューティング情報源追加要件定義書.md`, ADR-0069, ADR-0076

## コンテキスト

ADR-0069により、維津美の広場QAデータ専用の実データベース名は`chatbot`から`db_hiroba_qa`へ改名され、サーバ/ホスト名は`db_support_knowledge`（複数データソースDBを載せる基盤）へ改名済みである。ADR-0076により、この`db_hiroba_qa`実DBには新たにトラブルシューティング記事用テーブル（`troubleshooting_article`等）と、両データソースで共有するタグマスタが同居することになった。

この結果、実DB名`db_hiroba_qa`が「維津美の広場データ専用」という当初の意味と、実態（複数データソースを保持する）との間にズレが生じる。また、タグマスタ（`hiroba_tag`/`hiroba_tag_alias`/`hiroba_tag_folder`）も、名称上は「維津美の広場由来」を示す接頭辞を持ちながら、実態としてはデータソース非依存の共有マスタとして機能することになる。

発注者に、(1)実DB名を`db_chatbot_knowledge_base`へ再改名するか、(2)タグマスタ名を中立化するか、(3)実DB名再改名を行う場合の実施方式（ライブリネーム vs ADR-0069同様の再構築＋再インポート）、をそれぞれ確認した。特に(3)については、ADR-0069の実績上`terraform`の`var.db_name`変更がAWSでRDSインスタンスの置換（同一インスタンス上のconversationDBの再作成・再投入を含む）を伴うという情報を提示した上で確認し、発注者は「実DB名の再改名を行う」「タグマスタ名を中立化する」「実施方式はADR-0069と同方式の再構築＋再インポート」を選択した。

## 決定

**実データベース名を`db_hiroba_qa`→`db_chatbot_knowledge_base`へ再改名し、共有タグマスタ3テーブルを`hiroba_tag`→`tag`、`hiroba_tag_alias`→`tag_alias`、`hiroba_tag_folder`→`tag_folder`へリネームする。両方の変更を、ADR-0076の新規テーブル追加と合わせて単一の「再構築＋再インポート」サイクルで一度に適用する。**

1. **実DB名の値のみを変更**: `CHATBOT_DB_NAME`の値を`db_hiroba_qa`→`db_chatbot_knowledge_base`に変更する。変数名・ロール名・シークレット名・ダンプファイル名（`chatbot.sql`）・定数名（`CHATBOT_TABLES`）等、`chatbot`を冠する識別子の名称自体はADR-0069の方針を継続し変更しない。サーバ/ホスト名`db_support_knowledge`も変更しない。
2. **タグマスタ3テーブルのリネーム**: `hiroba_tag`/`hiroba_tag_alias`/`hiroba_tag_folder`を`tag`/`tag_alias`/`tag_folder`へリネームする。列名（`parent_tag_id`/`folder_id`/`display_order`等）・制約構造は変更しない。`hiroba_qa_tag`（維津美の広場QA側の結合テーブル）は改名せず、その`tag_id`外部キーの参照先のみ`tag(id)`に更新する。新設する`troubleshooting_article_tag.tag_id`も同じく`tag(id)`を参照する。
3. **単一の再構築サイクルへの統合**: ADR-0076の新規テーブル追加、本ADRの実DB名変更・タグマスタリネームを、1回のリリースでまとめて適用する。移行はADR-0069と同一の「再構築＋再インポート」方式（既存migrationファイルを新名称で書き換え、ローカルはボリューム破棄、AWSはDB用stateレイヤのdestroy+applyで作り直し、変換済みダンプを再インポート）を踏襲する。トラブルシューティング記事は既存データを持たないため、ダンプではなくHTMLインポート処理（要件定義書10章）で新規に投入する。
4. **ダンプ変換への追加**: `chatbot.sql`の構文限定置換に、`hiroba_tag`→`tag`、`hiroba_tag_alias`→`tag_alias`、`hiroba_tag_folder`→`tag_folder`の3パターンを追加する。列名（`tag_id`等）・CTEエイリアス（`tag_closure`）は引き続き対象外とする（ADR-0069の誤置換防止リストを継承・拡張する）。

## 検討した代替案

- **実DB名は変更せず、タグマスタのリネームと新テーブル追加のみを行う**: AWSでのRDSインスタンス置換（計画停止・conversationDB再投入を含む）というADR-0069で一度経験済みのコストを再度負担せずに済む。発注者にこの情報を提示した上で確認したが、発注者は実DB名が複数データソースを保持する実態を反映すべきという判断から、コストを許容の上で再改名を選択した。

- **実DB名の変更をPostgreSQLの`ALTER DATABASE ... RENAME TO ...`によるライブリネームで行う**: データを保持したまま即座にリネームでき、AWSでのRDSインスタンス置換を回避できる。ただし、terraformの`var.db_name`（`aws_db_instance`の初期データベース名指定）はリソース作成後は実体との対応を取れず、今後のterraform applyのたびに構成のズレ（ドリフト）が生じるか、`lifecycle.ignore_changes`等での特別な運用が必要になる。ADR-0069が「再構築＋再インポート」に一本化した経緯（ダンプからの完全復元を前提とし、二重の移行経路を持たない）とも整合しないため、発注者は本ADRでも再構築＋再インポート方式を選択し、本代替案は不採用とした。

- **タグマスタの名称は据え置き、`hiroba_`接頭辞のまま複数データソースで共有する**: リネーム作業（`knowledge_mcp`・`tag_selector_mcp`・`web_backend`・`db_hiroba_qa_init`にまたがるシステム横断の変更）が不要になり、変更範囲を最小化できる。ADR-0069が「実DB名とテーブル接頭辞の二重表現の冗長性は受容する」とした前例もある。しかし発注者は、タグマスタが名実ともにデータソース非依存の共有資産であることを明確にする方を選び、この機会に中立名称へのリネームを選択した。

## 結果・影響

- ADR-0069と同一の影響範囲（`db_hiroba_qa_init`・`knowledge_mcp`・`web_backend`・`tag_selector_mcp`・`docker-compose.yml`・`terraform`・`README.md`・`.env.example`）に加え、タグ関連の全SQL・DDL・テストが変更対象になる。
- AWSでは`var.db_name`変更に伴うRDSインスタンス置換（計画停止）が発生し、同一インスタンス上のconversationDBの再作成・`conversation.sql`再投入が必要になる（ADR-0069のOpen Issue #1と同種の運用計画が本件でも必要）。
- `db_hiroba_qa_init`の`CHATBOT_TABLES`（`import_data.py`）と`web_backend/src/export/tables.py`のテーブル一覧は、`tag`系リネームおよび`troubleshooting_article`系追加を反映した上で同期を保つ必要がある（ADR-0069で既知のリスクの継続）。
- `tag_selector_mcp/infrastructure/repository/tag_metadata_repository.py`の`hiroba_tag`/`hiroba_tag_alias`参照を`tag`/`tag_alias`へ更新する。
- 実DB名・タグマスタ名の変更は、ADR-0076のトラブルシューティング記事新設と同一リリースで適用され、再構築イベントを1回に集約する。
- `chatbot`を冠する識別子（ロール・シークレット・環境変数名・`chatbot.sql`・`CHATBOT_TABLES`）の名称は変更されない（ADR-0069の据え置き方針を継続）。
