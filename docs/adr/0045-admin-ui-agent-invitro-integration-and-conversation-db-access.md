# ADR-0045: admin_ui⇄agent_invitro間のチャット生成連携、およびconversationデータベースへの直接アクセス（ADR-0041の限定的な見直し）

- ステータス: Accepted
- 日付: 2026-08-24
- 関連: `docs/requirement/202608240949_AWS環境向けChatbotUI・会話評価機能有効化要件定義書.md`, ADR-0013, ADR-0023, ADR-0041, ADR-0042, ADR-0043, ADR-0044
- 参考（2026-08-21時点の廃案）: `docs/adr/_to_delete/0045-chatbot-ui-admin-ui-integration.md`（当時は評価機能も`agent_invitro`経由に一本化する案だったが、本ADRでは評価は`admin_ui`が直接処理する）

## コンテキスト

ADR-0043により、ChatbotUIの生成処理（`POST /ask-sl`）は`agent_invitro`が担うことになった。一方、発注者からの要望により、会話評価（good/bad、`POST /evaluate_response`, `GET /evaluated_messages`）は、ローカル`docker-compose`環境と同様、`admin_ui`（`web_backend`）が`conversation`データベースへ直接読み書きする分担を維持する。

ブラウザ（社内ネットワーク）から到達可能なAWSリソースは、既存の`admin_ui`サービス（ALB、社内IPアドレス限定、ADR-0041）のみである。`agent_invitro`はADR-0023の方針（VPC内部限定、外部公開なし）を維持するため、ALBから直接到達可能にはしない（ADR-0043の「検討した代替案」参照）。したがって、ブラウザからの`POST /ask-sl`は、`admin_ui`を経由して`agent_invitro`へ転送する必要がある。

また、ADR-0041は「`admin_ui`サービスからRDSへの直接アクセスは許可しない（ADR-0013の方針を維持）」と決定している。しかしこの決定はQAデータ（`chatbot`データベース）を対象にしたものであり、当時`conversation`データベースはAWS上に存在しなかった（本ADRの前提であるADR-0044により新設される）。会話履歴・評価データはKnowledge MCPの管理対象（QA・タグ）ではなく、ローカル環境でも元々`web_backend`が独自の`ConversationDB`クラスで直接扱ってきたデータであり、ADR-0013が定めた「QA検索はKnowledge MCP経由に統一する」という原則の対象外である。本ADRは、`conversation`データベースに限り、`admin_ui`からRDSへの直接アクセスを許可する例外を新設する（ADR-0041の限定的な見直し）。`chatbot`データベースへのアクセス経路（Knowledge MCP経由、ADR-0013）は変更しない。

さらに重要な制約として、`/ask-sl`・`/evaluate_response`・`/evaluated_messages`を実装する`main_stateless.py`は、ローカル`docker-compose`環境の`web_backend`コンテナとAWS環境の`admin_ui`コンテナの**両方が同一のソース**を実行している（`web_backend/Dockerfile`と`web_backend/Dockerfile.admin_ui`はビルド方法が異なるのみで、いずれも同じ`web_backend`ディレクトリをイメージに含める）。発注者からは「`/ask-sl`はローカルコンテナでは従来通りLM Studioを使い、AWSにデプロイした構成ではBedrock（＝`agent_invitro`経由）を使いたい。両立させたい」との要望があり、これは要件定義書4.2節（ローカル環境は変更しない）とも一致する。したがって`/ask-sl`の中継化は、コードを恒久的に書き換えるのではなく、**実行環境に応じて経路を切り替える条件分岐**として実装する必要がある。この条件分岐の方式自体が本ADRの決定事項の一部である（決定1参照）。

## 決定

**`admin_ui`（`web_backend`）の役割を、チャット生成については`agent_invitro`への薄い中継（リバースプロキシ）とし、会話評価についてはローカル環境と同一の直接データベースアクセスを維持する、という2つの異なる分担で実装する。**

1. **チャット生成の中継（環境に応じた条件分岐、AWS環境のみ有効化）**: `main_stateless.py`の`/ask-sl`ルートに、環境変数`AGENT_INVITRO_URL`の設定有無による分岐を追加する。
   - **`AGENT_INVITRO_URL`が設定されている場合（AWS環境、`admin_ui`）**: リクエストをそのまま`agent_invitro`の新設HTTPエンドポイント（ADR-0043、例: `http://agent_invitro:8300/ask-sl`）へ転送し、レスポンスをそのまま返す薄い中継（`httpx`等のHTTPクライアントを使用）を行う。`admin_ui`自身はチャット生成のためのLLM呼び出し・`chatbot`データベースへのクエリを一切行わない。
   - **`AGENT_INVITRO_URL`が未設定の場合（ローカル`docker-compose`環境、`web_backend`）**: 既存の直接処理（`SummarizeLLM`→`FormatQueryToEmbed`→`get_embedding`→`DB.search_similar`→`GenerateAnswerLLM`、いずれもLM Studio呼び出し）をそのまま維持する。コードの削除・置き換えは行わない。
   - この条件分岐は、同ファイルが既に採用している「`STATIC_DIR`の存在有無でSPAフォールバックの登録を切り替える」（ADR-0042）、および「AWS上では`DATABASE_URL`等を空文字fallbackにして起動時エラーを避ける」という既存の実装パターンと同じ考え方であり、新しい設計原則を持ち込むものではない。
   - Terraform側では、ローカル`docker-compose.yml`は`AGENT_INVITRO_URL`を設定しない（変更なし）。AWS側の`terraform/main/app/main.tf`の`module "admin_ui"`にのみ`AGENT_INVITRO_URL`を設定する（9.2節）。これにより実装は1つのコードベースのまま、環境ごとに異なる経路を自動的に選択する。
   - 既存の`/api/*`ルータ（QA・タグ管理, ADR-0013）・静的資産配信・SPAフォールバック（ADR-0042）には変更を加えない。
2. **会話評価の直接処理を維持**: `POST /evaluate_response`・`GET /evaluated_messages`は、`admin_ui`（`web_backend`）が既存の`ConversationDB`クラス（`web_backend/src/conversation_db/db.py`）を通じて`conversation`データベース（ADR-0044）へ直接読み書きする、ローカル`docker-compose`環境と同一の実装をAWS上でも維持する。`agent_invitro`は`conversation`データベースに一切アクセスしない。
3. **ネットワーク**:
   - `admin_ui_task`から`agent_invitro`（8300番）への到達性を許可するセキュリティグループルールを`terraform/modules/network`に追加する（既存の`agent_invitro → knowledge_mcp`ルールと同形式）。`agent_invitro`自体はALBのセキュリティグループからの到達性を持たない（ADR-0023準拠を維持）。
   - `admin_ui_task`からRDS（5432番）への到達性を許可するセキュリティグループルールを`terraform/modules/network`に追加する（ADR-0041の限定的な見直し）。このルールはセキュリティグループ・ポート単位の許可であり、`chatbot`データベースと`conversation`データベースをネットワークレベルで区別できない。したがって、`admin_ui`に注入する資格情報は`conversation`データベース用（`CONVERSATION_DB_URL`、ADR-0044）に限定し、`chatbot`データベースの資格情報（`DATABASE_URL`）は注入しない。これによりアプリケーションレベル（資格情報スコープ）で`chatbot`データベースへの到達を防ぐ。QAデータ（`chatbot`データベース）へのアクセス経路はKnowledge MCP経由（ADR-0013）のまま変更しない。
4. **`admin_ui`の環境変数・IAM**: 平文環境変数`AGENT_INVITRO_URL`と、secrets`CONVERSATION_DB_URL`（ADR-0044の`conversation_db_url_secret_arn`）を追加する。Bedrock関連の環境変数・IAM権限（`enable_bedrock`）は追加しない（`admin_ui`はLLMを直接呼ばないため`false`のまま変更しない）。
5. **アクセス制御**: ChatbotUI・会話評価機能へのアクセス制御（社内IPアドレス限定、追加ログイン認証なし）は、`admin_ui`の既存ALB・セキュリティグループ設定のまま変更しない（ADR-0041）。`agent_invitro`への転送、RDSへのアクセスはいずれもAWS内部のみで完結するため、この制御はブラウザからのリクエストに対して既存どおり機能する。

## 検討した代替案

- **評価機能も`agent_invitro`経由に一本化する（2026-08-21時点の廃案の方針）**: `admin_ui`のDB接続を一切なくせる利点があるが、発注者から今回「評価機能はこれまで通り`admin_ui`のバックエンドが直接クエリを発行してよい」との明確な要望があった。ローカル環境の既存実装（`admin_ui`が直接`ConversationDB`を扱う）をそのまま流用でき、変更範囲も小さいことから、この要望を優先し不採用とした。
- **ALBのパスベースルーティングで`agent_invitro`へ直接振り分ける**: `admin_ui`を介さずブラウザから`agent_invitro`へ直接到達させる構成。ADR-0023の「`agent_invitro`はALB非公開」という境界を広げる必要があり、発注者の意向（ADR-0023の境界をできるだけ維持したい）に反するため不採用とした。
- **`admin_ui`からRDSへの直接アクセスを一切許可しない（ADR-0041を維持し、`conversation`データベースも`agent_invitro`等の中間層を介する）**: 評価機能を今回の要望通り`admin_ui`に残す場合、この案は選択できない。将来的にADR-0013と同様のKnowledge MCP的な中間サービスを新設して統一する案は、本フェーズの規模（会話ログ・評価データの読み書きのみ）に対して過剰と判断し見送った。
- **`/ask-sl`の中継化を環境変数分岐にせず、ローカル用・AWS用に`main_stateless.py`自体を複製・分岐させる（`front_dev`の開発/本番用Dockerfile分離, ADR-0042と同様の発想）**: 検討したが、`/api/*`・`/evaluate_response`・`/evaluated_messages`・静的資産配信等、ファイルの大部分がローカル・AWSで完全に同一であり、ファイル自体を複製すると今後の変更の同期漏れ（片方だけ直してもう片方を直し忘れる）のリスクが増える。同ファイルが既に採用している「環境変数の有無による分岐」（`STATIC_DIR`, 空文字fallback等）と一貫した方式の方がリスクが小さいと判断し、`/ask-sl`ルートのみを`AGENT_INVITRO_URL`の有無で分岐させる方式（決定1）を採用した。

## 結果・影響

- `web_backend/main/main_stateless.py`の`/ask-sl`ルートに実装変更が発生する（`AGENT_INVITRO_URL`有無による分岐の追加、AWS側は`httpx`等による中継化）。既存のLM Studio直接呼び出し実装（`SummarizeLLM`, `FormatQueryToEmbed`, `get_embedding`, `DB.search_similar`, `GenerateAnswerLLM`）は削除せず、`AGENT_INVITRO_URL`未設定時のパス（ローカル`docker-compose`環境）としてそのまま残す。これにより、ローカル環境は従来通りLM Studioを使い、AWS環境はBedrock（`agent_invitro`経由）を使う、という発注者の要望（両立）を1つのコードベースで満たす。`/evaluate_response`・`/evaluated_messages`ルートは実装変更不要（既存実装がそのまま動作する。AWS上で`CONVERSATION_DB_URL`が実際の値を持つようになるため、既存の空文字fallback処理を維持したまま実質的に機能するようになる）。
- `terraform/main/app/main.tf`の`module "admin_ui"`に環境変数`AGENT_INVITRO_URL`、secrets`CONVERSATION_DB_URL`が追加される。`enable_bedrock`は変更しない（`false`のまま）。
- `terraform/modules/network`に、`admin_ui_task → agent_invitro`、`admin_ui_task → rds`の2つの新規到達性ルールが追加される。
- `admin_ui`が技術的にはRDSインスタンスへネットワーク到達可能になる点（`chatbot`データベースを含むインスタンス全体への到達性）は、ADR-0013が定めた「QA検索はKnowledge MCP経由に統一する」という原則に対する残存リスクとして残る。緩和策として資格情報スコープ（3節）を用いるが、将来的にネットワークレベルでも分離したい場合は、RDSインスタンス自体の分離（ADR-0044「検討した代替案」参照）を再検討する。
- ADR-0041が残した将来課題（社外拠点からの利用、認証方式の追加等）の位置づけは変更しない。
- `agent_invitro`の障害・過負荷時はChatbotUI（生成）のみが影響を受け、会話評価・QA・タグ管理UI（`admin_ui`内で直接処理）には影響しない。
