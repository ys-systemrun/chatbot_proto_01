# ADR-0028: AWSアカウント・リージョン等の環境固有設定の管理方式（Git管理外のterraform.tfvars）

- ステータス: Accepted
- 日付: 2026-08-10
- 関連: `docs/requirement/202608100910_MCPサーバークライアントAWSデプロイ要件定義書.md`, ADR-0027

## コンテキスト

Terraformで管理するAWSインフラの適用にあたり、AWSアカウントID・リージョンといった環境固有の値をどのようにコード管理するかを決める必要がある（要件定義書 Open Issue #6の一部）。これらの値はリポジトリに含めるべきではない環境依存情報であり、既存プロジェクトの`.env`/`.env.example`パターン（README.md記載）と同様の考え方を、Terraformの変数管理にも適用する必要がある。

検討した選択肢は次の3案。

1. **`terraform.tfvars`をGit管理外（`.gitignore`対象）とする**: 各実行者・環境ごとにローカルで用意し、リポジトリにはコミットしない。サンプルとして`terraform.tfvars.example`のみをコミットする。
2. **リポジトリにコミットされた変数ファイル**（例: `environments/verify.tfvars`）で管理する。
3. **AWS Systems Manager Parameter StoreやSecrets Managerで動的に保持し、Terraformの外部データソースとして取得する**。

## 決定

**`terraform.tfvars`をGit管理外とする方式（案1）を採用する。**（発注者確認済み）

AWSアカウントID・リージョン等の環境固有の値は、各実行者・実行環境ごとに用意する`terraform.tfvars`（`.gitignore`対象）に記述する。リポジトリには、必要な変数のキー名と説明のみを示す`terraform.tfvars.example`をコミットする（既存の`.env.example`と同様のパターン）。

## 検討した代替案

- **案2（リポジトリにコミットされた変数ファイル）**: 共有・可読性は高いが、AWSアカウントIDのような環境依存情報をリポジトリに残すことは望ましくないため不採用とした。
- **案3（Parameter Store/Secrets Manager等での動的管理）**: 複数環境・CI/CD運用が本格化した段階では有効な選択肢だが、本検証（MVP）のシンプルさを優先し、現時点では見送る。将来、CI/CD導入時（要件定義書スコープ外）に再検討する余地を残す。

## 結果・影響

- `.gitignore`に`terraform.tfvars`（および`*.tfvars`のうちサンプル以外）を追加する必要がある。
- 実装フェーズで`terraform.tfvars.example`を用意し、必要な変数（`aws_account_id`、`aws_region`等）のキー一覧とその説明を示す。
- 将来CI/CDを導入する場合、`terraform.tfvars`方式からCI側のシークレット管理・環境変数注入方式への切り替えが必要になる可能性がある点を留意事項として残す。
- AWSアカウントID・リージョンの具体的な値そのものは、本ADR（管理方式の決定）の対象外であり、実装フェーズで各実行者が`terraform.tfvars`に設定する。
