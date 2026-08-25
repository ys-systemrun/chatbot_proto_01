# ADR-0043: agent_invitroの常駐HTTPサービス化とチャット生成（/ask-sl）機能の実装移管

- ステータス: Accepted
- 日付: 2026-08-24
- 関連: `docs/requirement/202608240949_AWS環境向けChatbotUI・会話評価機能有効化要件定義書.md`, ADR-0013, ADR-0016, ADR-0017, ADR-0018, ADR-0019, ADR-0020, ADR-0021, ADR-0022, ADR-0023, ADR-0025, ADR-0031, ADR-0044, ADR-0045
- 参考（2026-08-21時点の廃案）: `docs/adr/_to_delete/0043-agent-invitro-http-service-chatbot.md`, `docs/adr/_to_delete/0045-chatbot-ui-admin-ui-integration.md`

## コンテキスト

ChatbotUI（`POST /ask-sl`）は現在、`web_backend`（`main_stateless.py`）が単独で次の処理を行っている。

1. 15件以上の会話履歴があれば、古い3件を要約（`SummarizeLLM`）
2. 検索クエリの整形（`FormatQueryToEmbed`）
3. embedding計算（`src/embedding.py:get_embedding`、ローカルLLM専用でプロバイダ分岐を持たない）
4. `chatbot`データベースへの直接クエリによる類似QA検索（`DB.search_similar`）
5. 回答生成（`GenerateAnswerLLM`）

いずれもローカルLLM（LM Studio）を直接呼び出す実装であり、Bedrock用の実装（`GenerateAnswerLLMBedrock`等、`web_backend/src/llm/`配下）は用意されているが`main_stateless.py`からは呼ばれていない。AWS上の`admin_ui`サービス（ADR-0041/0042）は`web_backend`と同一コンテナイメージで稼働しているため`/ask-sl`パス自体は既にALB経由で到達可能だが、必要な環境変数（`DATABASE_URL`, `LMSTUDIO_CHAT_URL`等）が未設定（空文字fallback、`main_stateless.py`）であり、呼び出すと実行時エラーになる。

一方、`agent_invitro`は既にLangGraphによるReActエージェント（ADR-0019〜0022）としてKnowledge MCP・Tag Selector MCPを自律的に呼び出す構成を持ち、AWS上でも`LLM_PROVIDER=bedrock`・`BEDROCK_CHAT_MODEL_ID`・`enable_bedrock=true`が既に設定済みで（`terraform/main/app/main.tf`）、Knowledge MCP・Tag Selector MCPへの到達性（セキュリティグループ）も確立している。しかし常駐HTTPサーバーではなく（`container_port = null`、`command = ["sleep","infinity"]`、ADR-0019/0025）、ALB・他サービスからの到達性は現状ゼロである。

2026-08-21頃、本件と同種の要件（要件定義書`_to_delete/202608211542`、ADR-0043/0044/0045 `_to_delete`）が一度検討されたが、実装着手前に取りやめられた。当時の方針転換の経緯では、ChatbotUI・会話評価機能の実処理（QA類似検索・回答生成・要約・評価データの読み書き）を`agent_invitro`に一本化する案（Rev.2）まで進んでいたが、発注者へのヒアリングによれば「当時はAWS環境の構成をよく理解していなかったため一度白紙にした」とのことであり、技術的な不整合が原因ではなかった。

今回、発注者から新たに次の要望が示された。

- `admin_ui`のバックエンドが、`/ask-sl`にポストされた質問データを使って`agent_invitro`へHTTPリクエストを送信し、チャットの生成を行わせる（`admin_ui`のバックエンドが`agent_invitro`に対するHTTPクライアントとなる）。
- 会話評価（good/bad）の機構は、これまでと同様に`admin_ui`のバックエンドが直接クエリを発行してよい。
- 本件はAWS環境専用であり、ローカルdocker-compose環境の構成は変更しない。

これは2026-08-21時点のRev.1（`admin_ui`がBedrockを直接組み込む）・Rev.2（`agent_invitro`が生成・評価の両方を担う）のいずれとも異なる第3の分担であり、本ADRはチャット生成（`/ask-sl`）の実装移管のみを対象とする（評価機能の分担はADR-0045）。

`agent_invitro`をチャット生成の実処理担当とするには、（1）常駐HTTPサーバー化（ADR-0019/0025の対象範囲の見直し）、（2）QA類似検索の実装方式（`web_backend`が行っていた`chatbot`データベースへの直接クエリ方式を持ち込むか、既存のKnowledge MCP `search_knowledge`ツール呼び出しに統一するか）、を決定する必要がある。

## 決定

**`agent_invitro`にAWS環境限定で常駐HTTPサーバー機能を追加し、`POST /ask-sl`と同一のAPI契約を持つチャット生成エンドポイントを実装する。** ローカルdocker-compose環境における`agent_invitro`の位置づけ（IPython対話シェル専用コンテナ、ADR-0019）は変更しない。

- **API契約の継続**: `POST /ask-sl`は、既存`web_backend`実装と同一のリクエスト・レスポンス形式（`Request{conversation_id, text, messages, summary}` → `Response{conversation_id, messages, summary}`、`Message{order, role, content, input, model, evaluation}`、`Summary{content, summarized_upto}`）を維持する。`front_dev`（ブラウザ側のコード）には変更を加えない。`/evaluate_response`・`/evaluated_messages`は`agent_invitro`に実装しない（ADR-0045参照、`admin_ui`が直接処理を継続する）。
- **QA類似検索**: `web_backend`が行っていた`chatbot`データベース（`chatbot-invitro-rds`）への直接クエリ（`DB.search_similar`）は持ち込まない。代わりに、既存のKnowledge MCP `search_knowledge`ツール（既にBedrockエンベディング対応済み、ADR-0031）を、`agent_invitro`が既存のMCPクライアント構成（ADR-0021）でそのまま呼び出す。これにより`agent_invitro`が`chatbot`データベースへ直接到達する必要がなくなる。
- **クエリ整形**: `web_backend`の`FormatQueryToEmbed`相当の明示的なクエリ整形ステップは持ち込まない。ReActエージェント（ADR-0022）が`search_knowledge`ツールを呼び出す際の検索クエリは、エージェント自身の推論によって組み立てられる。実装フェーズで、既存の明示的整形と比べて検索精度が損なわれないことを確認する（要件定義書12章Open Issue #1）。
- **会話要約**: `web_backend`の`SummarizeLLM`相当の要約ロジックは、`agent_invitro`側に複製実装する（コンポーネント間でコードを共有せず複製する既存方針、ADR-0016〜0018を踏襲）。既存のBedrockチャットクライアント（`LLM_PROVIDER=bedrock`, `BEDROCK_CHAT_MODEL_ID`、既にterraformで設定済み）をそのまま利用する。
- **回答生成**: 既存の`agent_invitro`のLangGraph ReActエージェント（Bedrock接続、ADR-0031で既に決定・設定済み）をそのまま利用する。単一プロンプトの生成呼び出し（`GenerateAnswerLLMBedrock`相当）に留めるか、エージェントのツール呼び出しループ全体を経由させるかは実装フェーズで確定するが、少なくとも検索は`search_knowledge`経由に統一する（本ADRの決定事項）。
- **会話履歴・評価データ**: `agent_invitro`は`conversation`データベース（ADR-0044）へ一切アクセスしない。現行の`/ask-sl`実装自体がステートレスであり`conversation`データベースへの読み書きを行っていないこと、および評価機能はADR-0045により`admin_ui`が直接処理する分担であることの両方から、`agent_invitro`に`conversation`データベースへの到達性を追加する必要はない。
- **ネットワーク・IAM**: `agent_invitro`のECSタスクに新規コンテナポート（8300番、既存の`knowledge_mcp`=8100・`tag_selector_mcp`=8200の命名規則を踏襲）を持たせ、ヘルスチェック（`/health`）を追加する。ALBからの到達性は与えない（ADR-0023「VPC内部限定」方針を維持）。`admin_ui`から`agent_invitro`への到達性のみを新設する（ADR-0045）。`agent_invitro`からRDSへの到達性は追加しない。既存の`enable_bedrock=true`・Knowledge MCP/Tag Selector MCPへの到達性は変更しない。
- **常駐化の実装方法**: `agent_invitro/Dockerfile`の`CMD ["sleep", "infinity"]`、ローカル`docker-compose.yml`の`command: ["sleep", "infinity"]`は変更しない。AWS環境限定の変更として、`terraform/main/app/main.tf`の`module "agent_invitro"`の`command`引数のみを、常駐HTTPサーバー起動コマンドへ変更する（既存の`variable "command"`はこの用途のために元々用意されている拡張点である）。

## 検討した代替案

- **2026-08-21時点の案（Rev.1: `admin_ui`に直接Bedrock組み込み／Rev.2: `agent_invitro`が生成・評価の両方を担う）**: いずれも実装着手前に取りやめられている。発注者への確認によれば、取りやめた理由はAWS環境構成の理解不足によるもので、技術的な不整合が原因ではなかった。今回、AWS環境の既存構成（ADR-0023, 0041等）を踏まえて再検討した結果、生成のみを`agent_invitro`へ委任し評価は`admin_ui`が直接処理する第3の分担が、既存のADR方針（ADR-0013「QA検索はKnowledge MCP経由」、ADR-0023「`agent_invitro`はVPC内部限定」）と最も整合し、かつ`agent_invitro`に評価用のRDSアクセス経路を持たせる必要がなくなる分、変更範囲が小さいと判断した。
- **`web_backend`のロジック（直接DBクエリ・埋め込み計算・クエリ整形）をそのまま`agent_invitro`へ移植する**: `search_knowledge`経由に統一する方式と比べ、既存の検索品質・挙動を完全に保持できる可能性が高いが、（1）`agent_invitro`に新たに`chatbot`データベースへの直接到達性・埋め込みのBedrock対応実装が必要になる、（2）既存のKnowledge MCPアーキテクチャ（QA検索はKnowledge MCP経由に統一する、ADR-0001〜0006の思想）から外れる、という理由で不採用とした。将来、`search_knowledge`経由での検索品質が不十分と判明した場合は、本ADRを見直し、クエリ整形ステップの追加やDB直接アクセスへの回帰を検討する。
- **ALBのパスベースルーティングで`agent_invitro`へ直接振り分ける**: `admin_ui`を介さずブラウザから`agent_invitro`へ直接到達させる構成。ALB・Terraformの変更範囲は増えるが`admin_ui`を完全に静的配信専用にできる。ADR-0023の「`agent_invitro`はVPC内部限定・ALB非公開」という境界をできるだけ維持したいという意向により、`admin_ui`が薄い中継を担う方式（ADR-0045）を採用し、本方式は不採用とした。

## 結果・影響

- `agent_invitro/src/`にアプリケーションコードの変更が発生する（HTTPサーバーエントリポイントの追加、会話要約ロジックの複製実装）。既存の`main.py`（IPythonから呼び出すエントリポイント）は変更しない。具体的な変更内容は実装指示書で指示する。
- `agent_invitro/Dockerfile`・ローカル`docker-compose.yml`は変更しない。`terraform/main/app/main.tf`の`module "agent_invitro"`に`container_port = 8300`、`health_check_command`が追加され、`command`引数が常駐HTTPサーバー起動コマンドへ変更される。
- `terraform/modules/network`に、`admin_ui_task → agent_invitro`（新設8300番ポート）への到達性ルールが追加される（ADR-0045）。`agent_invitro → rds`のルールは追加しない。
- ADR-0019・ADR-0025が定めた「常駐HTTPサーバー化はしない」という決定は、AWS環境に限り本ADRの範囲で見直される。ローカルdocker-compose環境における位置づけ（IPython対話シェル専用コンテナ）はADR-0019のまま変更しない。ADR-0019・ADR-0025自体のファイルは変更しないが、AWS環境における以後の判断は本ADRを優先する。
- QA検索精度（`search_knowledge`経由でクエリ整形ステップを省略した場合の精度）の検証が実装フェーズで必要になる（要件定義書12章Open Issue）。
