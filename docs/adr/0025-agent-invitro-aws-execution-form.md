# ADR-0025: `agent_invitro`のAWS上での実行形態（ECS Fargate常駐化・ECS Exec方式）

- ステータス: Accepted
- 日付: 2026-08-10
- 関連: `docs/requirement/202608100910_MCPサーバークライアントAWSデプロイ要件定義書.md`, ADR-0019, ADR-0023, ADR-0024

## コンテキスト

ADR-0019は、`agent_invitro`の実験フェーズにおける実行形態として、常駐HTTPサーバー化を時期尚早と判断し、`tty: true`でコンテナを起動させ続け、開発者が`docker compose exec agent_invitro ipython`で接続して対話的に手動実行する形態を採用した。同ADRは「将来、本番Conversation Agentとして常駐HTTPサーバー化する場合は、ADR-0002・ADR-0007と同様の方針であらためて実行形態を決定する」と明記し、判断を先送りしていた。

今回、`knowledge_mcp`・`tag_selector_mcp`とともに`agent_invitro`をAWS上にデプロイし、AWS上での動作検証を行う（ADR-0023, 0024）にあたり、ローカルの`docker compose exec`という接続手段はAWS上では成立しないため、AWS上での実行形態をあらためて決定する必要がある。ただし、これは「本番Conversation Agent化」（Web API化、会話履歴管理等を伴う大きな設計判断）とは区別し、あくまで**動作検証目的でのAWS上での実行形態**として決定する。

検討した選択肢は次の3案。

1. **ECS Fargate常駐サービス化 + ECS Exec**: `agent_invitro`をECS Fargateサービスとして常駐させ、動作確認は`aws ecs execute-command`（ECS Exec）でコンテナ内シェルに接続し、IPython等で対話的に実行する。ADR-0019の「対話シェルによる手動実行」という検証方針は維持し、接続手段のみ`docker compose exec`から`ECS Exec`に置き換える。
2. **常駐HTTPサーバー化（本番相当のAPI化）**: 外部からのリクエストを受け付けるAPIとして`agent_invitro`を公開する。
3. **ローカルdocker-compose環境からAWS上のMCPエンドポイントへ接続し、`agent_invitro`自体はAWSに置かない**。

## 決定

**案1（ECS Fargate常駐サービス化 + ECS Exec方式）を採用する。**（発注者確認済み）

`agent_invitro`はECS Fargateサービスとして常駐させ、`knowledge_mcp`・`tag_selector_mcp`と同一VPC内でECS Service Connect経由で両MCPサーバーに接続する。動作確認はECS Exec（`aws ecs execute-command`）でコンテナ内シェルに接続し、IPython等で対話的にLangGraphのグラフを手動実行する形態とする。常駐HTTPサーバー化（外部からのリクエストを受け付けるAPIとしての公開）は本ADRの対象外とし、必要になった時点で別途ADRを起票する。

## 検討した代替案

- **案2（常駐HTTPサーバー化）**: 本番相当の実装であり、API仕様・セッション管理・会話履歴の扱い等、多くの設計判断を新たに伴う。今回の目的（AWS上でMCP接続・ツール呼び出しが機能することの検証）に対しては過剰であり、検証速度を優先して見送った。ADR-0019が示す「将来の本番化」に該当するため、判断は先送りする。
- **案3（`agent_invitro`をAWSに置かず、ローカルからAWS上のMCPエンドポイントへ接続）**: ADR-0023で「オンプレ社内LANとAWS VPC間の新規接続（VPN等）は本フェーズで構築しない」ことが既に確定しているため、この案はその前提と矛盾し、成立しない。不採用。

## 結果・影響

- `agent_invitro`のECS Fargateタスク定義に、ECS Exec用の設定（`enableExecuteCommand`等）を含める必要がある。
- ECSタスクロール・実行ロールに、ECS Exec（Systems Manager経由のセッション確立）に必要なIAM権限を付与する必要がある。
- ADR-0019で確定した「対話シェルによる手動実行」という検証方針自体（IPythonの採用含む）は維持されるため、`agent_invitro`のアプリケーションコード側の変更は最小限（接続先MCPエンドポイントのURL・実行環境の差異のみ）と想定される。
- 常駐HTTPサーバー化（本番Conversation Agent化）は本ADRの対象外であり、必要になった時点でADR-0002・ADR-0007・本ADRを踏まえて別途ADRを起票する。
