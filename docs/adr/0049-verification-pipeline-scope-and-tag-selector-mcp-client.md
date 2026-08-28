# ADR-0049: 検証実行パイプラインの範囲とTag Selector MCPクライアントの新設

- ステータス: Accepted
- 日付: 2026-08-26
- 関連: `docs/requirement/202608260909_質問タグ情報源検索精度検証機能要件定義書.md`, ADR-0009, ADR-0010, ADR-0013, ADR-0019, ADR-0021, ADR-0022, ADR-0043

## コンテキスト

検証機能（「質問→タグ→情報源」を確認する機能、要件定義書1章）の実行時に、どの処理を呼び出すかについて、次の3案が考えられた。

1. `tag_selector_mcp`の`select_tags`と`knowledge_mcp`の`search_knowledge`を、`web_backend`から順に直接呼び出す（回答生成・要約・会話履行は含めない、検索部分のみ）。
2. `agent_invitro`（LangGraph ReActエージェント, ADR-0019〜0022）へ質問を投げ、エージェントが自律的に呼び出したツール（`select_tags`・`search_knowledge`を含む可能性がある）の呼び出し内容を記録する。
3. 上記の両方を実行できるようにし、比較できるようにする。

発注者に確認した結果、「`tag_selector_mcp`→`knowledge_mcp`の2段検索のみ」（案1）との回答を得た（要件定義書2章 回答3）。

`agent_invitro`のReActエージェントは、LLMが状況に応じて自律的にツールを選ぶ方式（ADR-0022）であり、`select_tags`を呼ぶかどうか・どのような引数で呼ぶか・`search_knowledge`を何回呼ぶか等はエージェントの推論に依存し、実行ごとに変動しうる。要件が求める「質問→タグ→情報源」という固定順・固定入出力の観測（1質問につき1回の`select_tags`結果と1回の`search_knowledge`結果を対応づけて記録する、要件定義書6.3節）には、案1の直接呼び出し方式が構造的に一致する。

一方、`web_backend`は現時点で`knowledge_mcp`をMCPクライアントとして呼び出す実装（`KnowledgeMcpClient`, `qa_controller`/`tag_controller`が利用）を持つが、`tag_selector_mcp`を呼び出す実装は持たない。`tag_selector_mcp`の既存の呼び出し元は`agent_invitro`のみである（`docker-compose.yml`の`TAG_SELECTOR_MCP_URL`は`agent_invitro`にのみ設定されている）。

## 決定

**検証実行は、`web_backend`が`tag_selector_mcp`の`select_tags`→`knowledge_mcp`の`search_knowledge`を順に直接呼び出す2段パイプラインのみを対象とする。`agent_invitro`経由の実行、および回答生成（LLMによる最終回答文生成）は対象外とする。** これを実現するため、`web_backend`に新規`TagSelectorMcpClient`（`web_backend/src/mcp_client/tag_selector_mcp_client.py`）を追加する。

- **`TagSelectorMcpClient`の実装方式**: 既存の`KnowledgeMcpClient`（`web_backend/src/mcp_client/knowledge_mcp_client.py`）と全く同一の方式を踏襲する。すなわち、MCP Python SDKのStreamable HTTPクライアントを用い、呼び出しごとに新規セッションを張り処理完了後にクローズする（コネクションプールは維持しない）。業務エラー（`ToolError`相当）は専用の例外（`TagSelectorMcpError`）へ変換し、接続失敗・タイムアウト等の基盤エラーはラップせずそのまま送出する。
- **呼び出し順序と引数**: `select_tags(query=質問文, max_tags, confidence_threshold)` を呼び、返された`SelectedTag`一覧の`name`を`search_knowledge(query=質問文, tags=タグ名一覧, top_k, min_score)`の`tags`引数として渡す。`max_tags`・`confidence_threshold`・`top_k`・`min_score`は`web_backend`側の環境変数（要件定義書6.3節・9章）で指定し、実際に使用した値を`verification_run`に記録する（ADR-0050、再現性のため）。
- **対象外とする処理の明確化**: `agent_invitro`への到達性（新規ネットワーク経路）は本ADRの範囲では追加しない。回答生成（`GenerateAnswerLLM`相当）・会話要約・会話履行の保存は検証実行に含めない。
- **ネットワーク・環境変数（AWS）**: `admin_ui_task`（`web_backend`のAWS上のサービス）から`tag_selector_mcp`（8200番）への到達性を許可するセキュリティグループルールを新設する。これは既存の`admin_ui_task → knowledge_mcp`（ADR-0013/0041）、`agent_invitro → tag_selector_mcp`（ADR-0021の実行に必要な既存ルール）と同形式であり、新しい設計原則を持ち込むものではない。`admin_ui`から`tag_selector_mcp`への到達性は本ADRが初めて必要とするものである。

## 検討した代替案

- **`agent_invitro`経由での検証（案2）**: 実際の`/ask-sl`（AWS環境, ADR-0043）に近い経路で検証できる利点がある。しかし、ReActエージェントの自律的なツール選択（ADR-0022）により、「質問ごとに必ず1回の`select_tags`と1回の`search_knowledge`が対応する」という要件定義書が求める観測粒度を保証できない（エージェントが`select_tags`を呼ばずに`search_knowledge`のみを呼ぶ、複数回呼ぶ、あるいは全く別のクエリ文字列を組み立てて呼ぶ可能性がある）。加えて`agent_invitro`は現時点でALB非公開（VPC内部限定、ADR-0023）であり、`admin_ui`から`agent_invitro`への新規到達性（ADR-0043/0045と同様の中継構成）が必要になり、変更範囲が案1より大きい。発注者の回答（案1）とも合致しないため不採用とした。
- **両方式を実装し比較可能にする（案3）**: 将来的な価値はあるが、MVPの実装コストが2倍近くになる。発注者の回答は案1のみを求めており、過剰と判断し見送った。将来、`agent_invitro`側の実際の挙動（クエリ整形の有無等、ADR-0043「結果・影響」のOpen Issueにある検索精度確認）を検証したいニーズが生じた場合に、案2を追加する形で再検討する。
- **`web_backend`から`tag_selector_mcp`を、既存の`KnowledgeMcpClient`を汎用化・共通化した単一クラスで呼び出す**（`TagSelectorMcpClient`を新設せず、`McpClient(url)`のような汎用クラスに統合する）: コードの重複を減らせる利点があるが、既存の`agent_invitro`側は`langchain-mcp-adapters`（ADR-0021）を使い、`web_backend`側は独自の薄いラッパー（`KnowledgeMcpClient`）を使うという、コンポーネントごとに実装を複製する既存方針（ADR-0016〜0018等で繰り返し採用されている「コンポーネント間でコードを共有しない」方針）と、`web_backend`内での2クライアントの統合は矛盾しないが、`KnowledgeMcpError`/`TagSelectorMcpError`のように呼び出し先ごとに例外型を分けている既存の設計（`app.py`の`@app.exception_handler(KnowledgeMcpError)`）との一貫性を優先し、既存コードに合わせて`KnowledgeMcpClient`と対になる`TagSelectorMcpClient`を新設する方式を採用した。

## 結果・影響

- `web_backend/src/mcp_client/tag_selector_mcp_client.py`（新規）、`web_backend/src/mcp_client/__init__.py`への export追加が発生する。既存の`knowledge_mcp_client.py`には変更を加えない。
- `web_backend/src/main/controllers/verification_controller.py`（新規）が、`TagSelectorMcpClient`・既存`KnowledgeMcpClient`の両方を呼び出すオーケストレーション（要件定義書6.3節）を行う。
- ローカル`docker-compose.yml`の`web_backend`サービスに`TAG_SELECTOR_MCP_URL`環境変数・`tag_selector_mcp`への`depends_on`が追加される。AWS側は`terraform/main/app/main.tf`の`module "admin_ui"`に同環境変数が追加され、`terraform/modules/network`に`admin_ui_task → tag_selector_mcp`の到達性ルールが新規追加される。
- `tag_selector_mcp`・`knowledge_mcp`自体のコード・ツール仕様（`select_tags`/`search_knowledge`の入出力）には変更を加えない。
- `agent_invitro`の障害・過負荷は本機能に影響しない（依存しないため）。逆に、本機能による`tag_selector_mcp`・`knowledge_mcp`への追加の呼び出し負荷が、既存の`agent_invitro`経由の呼び出し（ADR-0043のチャット生成）と競合するリスクがある。運用開始後、検証実行の頻度が高い場合はこの点を監視する必要がある（要件定義書12章Open Issue #5と関連）。
