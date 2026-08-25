# app 構成の変数（ADR-0039 §5.2）。
#
# ADR-0038/0040: 全変数は terraform/.env（AWS_REGION / AWS_ACCOUNT_ID / NAME_PREFIX / STATE_BUCKET
# と TF_VAR_*）に一元化し、deploy（コンテナ内 Python）が TF_VAR_* 環境変数として供給する。
# 手動 apply する場合は `deploy shell`（環境設定済みのコンテナ内 bash）から実行する。

# --- 共通値（ADR-0038, .env の TF_VAR_* から供給）---
variable "aws_region" {
  type        = string
  description = "デプロイ先リージョン（provider / terraform_remote_state / 各タスク定義に使用）"
}

variable "aws_account_id" {
  type        = string
  description = "デプロイ先 AWS アカウントID（発注者から受領, ADR-0038）"
}

variable "name_prefix" {
  type    = string
  default = "chatbot-verify"
}

# terraform_remote_state（database 構成）参照用の S3 バケット名。ADR-0038: .env の TF_VAR_state_bucket から供給。
variable "state_bucket" {
  type        = string
  description = "Terraform state を保管する S3 バケット名（database 構成 state の参照に使用）"
}

# ADR-0039: app 構成は database 構成の出力を terraform_remote_state で参照する（片方向依存）。
# その state key。terraform/.env の STATE_KEY_DATABASE（deploy が TF_VAR_state_key_database として供給）から与えられる。
variable "state_key_database" {
  type        = string
  default     = "database/state.tfstate"
  description = "database 構成の state key（terraform_remote_state 参照用, ADR-0039 §5.2）"
}

# --- ECR イメージタグ（§5.2, latest 固定に頼らず明示推奨）---
variable "image_tag" {
  type    = string
  default = "latest"
}

# 検証用 MCP Inspector イメージのタグ
variable "mcp_inspector_image_tag" {
  type    = string
  default = "latest"
}

# Phase 4→5 ゲート用（apply-app / apply-all が制御）。seed 完了まで 0、完了後 1 にスケールする。
# 手動 apply 時は既定 1 のままでよい（その場合は seed 完了を手順で担保, README）。
variable "knowledge_mcp_desired_count" {
  type    = number
  default = 1
}

# --- Service Connect ---
variable "service_namespace" {
  type    = string
  default = "chatbot.internal"
}

# --- Bedrock（ADR-0031, モデルIDは実装時に確定）---
variable "bedrock_chat_model_id" {
  type        = string
  description = "チャット用 Bedrock モデルID（tag_selector_mcp / agent_invitro）"
}

variable "bedrock_embedding_model_id" {
  type        = string
  description = "埋め込み用 Bedrock モデルID（knowledge_mcp）"
}

# db_init のシード計算は database 構成へ移設したが、ADR-0038 の共通必須チェック（Test-Tfvars）と
# そろえるため app 構成でも宣言する（app 構成の .tf では未使用）。
variable "embedding_vector_dim" {
  type        = number
  description = "埋め込みモデルの出力次元（§6.2, ADR-0017。app 構成では未使用）"
}

# --- admin_ui（管理UI, ADR-0041）---
# ALB（sg-admin-ui-alb）への 80 番インバウンドを許可する社内IP（CIDR形式のリスト）。
# 0章の残 Open Issue（発注者から受領）が解消するまで値未確定。既定 [] のときは誰も到達できない。
variable "admin_ui_allowed_cidrs" {
  type        = list(string)
  default     = []
  description = "admin_ui ALB へのインバウンドを許可する社内IP（CIDR リスト, ADR-0041, 6.1節）"
}

# --- Bedrock コスト予算アラート（cost-alert モジュール）---
variable "bedrock_monthly_budget_usd" {
  type        = number
  default     = 50
  description = "Bedrock の月額予算（USD）。実額80% / 予測100% でメール通知。"
}

variable "budget_alert_emails" {
  type        = list(string)
  default     = []
  description = "予算アラートの通知先メール。空なら予算アラートを作成しない。"
}
