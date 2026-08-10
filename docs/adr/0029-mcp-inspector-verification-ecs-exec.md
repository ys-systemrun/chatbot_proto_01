# ADR-0029: MCP Inspectorによるプロトコル層検証の実行方式（ECS Execによる一時検証タスク）

- ステータス: Accepted
- 日付: 2026-08-10
- 関連: `docs/requirement/202608100910_MCPサーバークライアントAWSデプロイ要件定義書.md`, ADR-0023, ADR-0024, ADR-0025

## コンテキスト

要件定義書9.2節「プロトコル層の検証」では、MCP Inspector（MCP公式の開発者向け検証ツール）をAWS上の`tag_selector_mcp`・`knowledge_mcp`のエンドポイントに向けて実行し、`tools/list`・`tools/call`が正しく応答することを確認する方針としていた。しかし、ADR-0023によりAWS内部限定（外部公開なし）の構成であるため、MCP Inspector自体をどこから実行するかが課題として残っていた（要件定義書 Open Issue #5）。

検討した選択肢は次の2案。

1. **ECS Execで一時的に起動した検証用タスクから実行する**: MCP Inspectorをインストールした検証用のECS Fargateタスクを一時的に起動し、`aws ecs execute-command`（ECS Exec）でタスク内のシェルに接続してMCP Inspectorを実行する。
2. **SSMポートフォワーディングで、開発者のローカル端末からMCP Inspectorを実行する**: AWS Systems Manager Session Managerのポートフォワーディング機能を使い、ローカルのMCP InspectorからVPC内部のMCPエンドポイントへ疎通させる。

## 決定

**案1（ECS Execで一時的に起動した検証用タスクから実行する）を採用する。**（発注者確認済み）

MCP Inspectorをインストールした検証用タスク定義を用意し、必要な時にECS Fargateで一時的に起動する。ECS Exec（`aws ecs execute-command`）でタスク内のシェルに接続し、そこからMCP Inspectorを実行して、ECS Service Connect経由の内部エンドポイント（`tag_selector_mcp`・`knowledge_mcp`）に対して`tools/list`・`tools/call`を実行する。検証終了後は当該タスクを停止する。

## 検討した代替案

- **案2（SSMポートフォワーディング）**: 開発者のローカル端末上のMCP Inspector（ブラウザUIを含む）をそのまま使える利便性はあるが、開発者ごとにポートフォワード設定・AWS CLI/SSMプラグインのセットアップが必要になる。案1であれば、VPC内で完結する検証用タスクとAWS CLIの標準機能（ECS Exec）のみで実行でき、開発者の端末環境に依存しないため、こちらを優先する。

## 結果・影響

- MCP Inspectorを含む検証用タスク定義（Dockerイメージ）を新たに用意する必要がある。Terraformモジュール構成（要件定義書6.5節）に、この検証用タスク定義を追加する（常駐サービスではなく、必要時に起動・停止する一時的なタスクとして管理する）。
- 当該タスクには`enableExecuteCommand`設定と、ECS Exec（SSMセッション確立）に必要なIAM権限を付与する（ADR-0025で`agent_invitro`に適用した設定と同様の考え方を踏襲する）。
- 検証用タスクは常時稼働させず、検証実施時にのみ起動・終了する運用とし、コストへの影響を抑える。
- 具体的な起動・停止の運用手順（`aws ecs run-task`の実行手順等）は実装フェーズで確定する。
