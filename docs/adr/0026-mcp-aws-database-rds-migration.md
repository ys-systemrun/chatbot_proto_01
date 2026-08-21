# ADR-0026: 既存DB（pgvector）のAWS上での配置方針（Amazon RDS for PostgreSQLへ移行）

- ステータス: Accepted
- 日付: 2026-08-10
- 関連: `docs/requirement/202608100910_MCPサーバークライアントAWSデプロイ要件定義書.md`, ADR-0003, ADR-0023, ADR-0024

## コンテキスト

`knowledge_mcp`は、既存の`chatbot_db`（PostgreSQL + pgvector拡張、ADR-0003でベクトルストアとして採用済み）に依存している。`knowledge_mcp`をAWS上のECS Fargateサービスとしてデプロイする（ADR-0024）にあたり、この依存先DBをAWS上のどこに配置するかを決める必要がある（要件定義書 Open Issue #4）。

ここで、ADR-0023により「オンプレ社内LANとAWS VPC間の新規接続（VPN／専用線等）は本フェーズでは構築しない」ことが既に確定している。仮に`chatbot_db`を現状のまま（ローカルdocker-compose環境や社内LAN上）に残した場合、AWS上の`knowledge_mcp`からこのDBへ到達するためには、結局ADR-0023で見送った経路（AWSと社内LAN間の新規接続）が必要になり、前提と矛盾する。したがって、DBの配置についても「AWS上に置く」以外の選択肢は、ADR-0023の方針のもとでは実質的に成立しない。

その上で、AWS上でのDBの実行形態として次の2案を検討した。

1. **Amazon RDS for PostgreSQL（pgvector拡張）へ移行する**: マネージドサービスとしてPostgreSQLを運用し、pgvector拡張を有効化する。バックアップ・パッチ適用・可用性設定（Multi-AZ等）をAWS側の管理機能に委ねられる。
2. **既存のdocker-compose `db`サービスと同等の構成を、EC2インスタンスまたはECS Fargate上のコンテナとして自前運用する**: 既存構成（PostgreSQL + pgvectorコンテナ、ADR-0003）をそのままAWS上のコンテナとして再現する。

## 決定

**Amazon RDS for PostgreSQL（pgvector拡張）へ移行する。**（発注者確認済み）

`knowledge_mcp`が利用するDBは、ECS Fargateサービスと同一VPC内のプライベートサブネット（DBサブネットグループ）に配置したRDSインスタンスとする。RDSへの到達は`knowledge_mcp`からのみ許可し、他コンポーネント（`tag_selector_mcp`・`agent_invitro`）から直接DBへアクセスすることはない（既存構成と同様、DBアクセスは`knowledge_mcp`経由に閉じる）。

## 検討した代替案

- **案2（自前運用コンテナ）**: 既存のdocker-compose構成に最も近い形を再現できるが、パッチ適用・バックアップ・可用性確保を自前で設計・運用する必要があり、本検証（動作確認）の目的に対して運用負荷が見合わない。マネージドサービスであるRDSを使うことで、この運用コストを回避できる。
- **Amazon Aurora PostgreSQL（pgvector対応）**: RDS for PostgreSQLと同様にpgvector拡張が利用でき、読み取りレプリカ等のスケーリング機能に優れるが、MVPの動作検証という本フェーズの目的に対しては構成・コストの両面で過剰と判断し、まずは通常のRDS for PostgreSQLを採用する。将来、性能要件が明確になった段階で移行を再検討する余地は残す。

## 結果・影響

- Terraformのモジュール構成（要件定義書6.5節）に、RDSインスタンス・DBサブネットグループ・DB用セキュリティグループを含む`database`（または`rds`）モジュールの追加が必要になる。
- DB認証情報（マスターパスワード等）は、要件定義書6.6節の方針に合わせてAWS Secrets Managerで管理し、`knowledge_mcp`のECSタスク定義から`secrets`参照で注入する。
- 既存データ（QA・タグ等）をRDSへ投入する手順（マイグレーション・シード）をどう実行するかが新たな論点になる。既存の`db_hiroba_qa_init`（ADR-0016〜0018、yoyo-migrations採用）の仕組みをAWS上でも利用するか、あるいは本検証では最小限のデータのみをVPC内部から手動投入するかは、要件定義書のOpen Issueとして別途整理する。
- ローカルのdocker-compose環境（既存の`db`サービス、ADR-0003）には影響しない。本ADRはAWS環境限定の決定であり、ローカル開発フローと並行して存在する。
- RDSは常時起動する課金対象リソースであるため、検証終了後の削除（`terraform destroy`等）を含むコスト管理方針は、要件定義書のコスト関連Open Issueと合わせて確定する。

**（追記, 2026-08-17）** DB実体（RDSインスタンス等）を、ネットワーク層・アプリケーション層とは別の独立したTerraform stateに分離し、通常の`terraform destroy`運用（コスト管理目的）の対象から除外する方針を、ADR-0037として別途決定した。本ADRが決定した「RDSへ移行する」「同一VPC内に配置する」という内容自体に変更はないが、これを管理するTerraform state・destroy運用は単一state・都度全破棄という前提から更新されている。あわせて、DBを配置するVPCは、ADR-0036により既存VPCを外部参照する方式に変更されている（本ADR決定時点では新規VPC作成を前提としていた）。
