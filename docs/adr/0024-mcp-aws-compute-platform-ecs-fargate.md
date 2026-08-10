# ADR-0024: MCPサーバー・クライアント群のコンピュート基盤（ECS Fargate採用）

- ステータス: Accepted
- 日付: 2026-08-10
- 関連: `docs/requirement/202608100910_MCPサーバークライアントAWSデプロイ要件定義書.md`, ADR-0002, ADR-0007, ADR-0019, ADR-0023

## コンテキスト

`knowledge_mcp`・`tag_selector_mcp`・`agent_invitro`をAWS上にデプロイするにあたり、コンピュート基盤を決める必要がある。既存3コンポーネントはいずれも独立Dockerコンテナとして稼働する設計（ADR-0002, ADR-0007, ADR-0019）であり、Streamable HTTP（SSEベース）による長時間コネクションを前提としている。

検討した選択肢は次の3案。

1. **ECS Fargate**: 既存のDockerイメージをそのままタスクとして起動できるコンテナ実行基盤。サーバー管理が不要。
2. **AWS Lambda**: コンテナイメージにも対応するが、実行時間上限・コールドスタートがあり、Streamable HTTP/SSEのような長時間コネクションの維持には不向き。
3. **Amazon EKS**: Kubernetesベースのコンテナ実行基盤。柔軟性は高いが、3サービス規模の構成に対してクラスタ運用のオーバーヘッドが大きい。

## 決定

**ECS Fargateを採用する。**（発注者確認済み）

`knowledge_mcp`・`tag_selector_mcp`・`agent_invitro`の3コンポーネントを、それぞれECS Fargateサービスとして構築する。既存のDockerイメージをほぼそのまま利用し、サービス間の名前解決はECS Service Connect（またはAWS Cloud Map）で行う（要件定義書6.2節）。

## 検討した代替案

- **Lambda**: 既存Dockerイメージのコンテナイメージ対応はあるが、MCPサーバーが前提とするStreamable HTTP/SSEの長時間コネクションと、Lambdaの実行時間上限・コールドスタート特性が噛み合わない。イベントトリガー設計も新たに必要になり、既存の「常駐コンテナ」という設計方針（ADR-0002, 0007）からの乖離が大きいため不採用。
- **EKS**: コンテナオーケストレーションとしての柔軟性は高いが、3サービス程度の規模に対してクラスタ構築・運用（コントロールプレーンの管理、ノード管理等）のコストが過大である。将来的にコンポーネント数が大きく増える場合は再検討の余地があるが、本フェーズでは不採用とする。

## 結果・影響

- Terraformのモジュール構成（要件定義書6.5節）は、ECS Fargate向けの`ecs-cluster`・`ecs-service`モジュールを前提とする。
- サービス間通信の名前解決には、ECS Service Connect / AWS Cloud Mapの導入が必要になる（要件定義書6.2節）。
- ECSタスクロール・実行ロールのIAM権限設計（CloudWatch Logsへの書き込み、Secrets Managerからの読み取り、Bedrock利用時の呼び出し権限等）が必要になる（要件定義書10章）。
- Fargateは常時起動する構成のため、検証期間中のコストが発生する。検証終了後の破棄方針（`terraform destroy`等）は要件定義書のOpen Issue（コスト方針）として別途確定する。
- `agent_invitro`をECS Fargateサービスとして常駐化する場合の実行形態の詳細は、別ADR（ADR-0025）で扱う。
