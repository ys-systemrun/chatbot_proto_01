variable "aws_account_id" {
  type        = string
  description = "デプロイ先 AWS アカウントID（発注者から受領, Open Issue #6）"
}

variable "aws_region" {
  type        = string
  description = "デプロイ先リージョン（発注者から受領, Open Issue #6）"
}

# Phase 4→5 ゲート用（deploy.ps1 が制御）。seed 完了まで 0、完了後 1 にスケールする。
# 手動 apply 時は既定 1 のままでよい（その場合は seed 完了を手順で担保, README §Phase4/5）。
variable "knowledge_mcp_desired_count" {
  type    = number
  default = 1
}

variable "name_prefix" {
  type    = string
  default = "chatbot-verify"
}

# --- network（§5.1）---
variable "vpc_cidr" {
  type    = string
  default = "10.20.0.0/16"
}

variable "availability_zones" {
  type        = list(string)
  description = "2つ以上（RDS サブネットグループ要件）"
}

variable "enable_nat_gateway" {
  type    = bool
  default = false
}

# --- database（§5.3, 実装時に確定）---
variable "rds_engine_version" {
  type        = string
  description = "pgvector 対応の PostgreSQL バージョン（AWS 公式で要確認）"
}

variable "rds_instance_class" {
  type    = string
  default = "db.t4g.micro"
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

# --- Service Connect ---
variable "service_namespace" {
  type    = string
  default = "chatbot.internal"
}

# --- Bedrock（ADR-0031, モデルIDは実装時に確定 Open Issue #5）---
variable "bedrock_chat_model_id" {
  type        = string
  description = "チャット用 Bedrock モデルID（tag_selector_mcp / agent_invitro）"
}

variable "bedrock_embedding_model_id" {
  type        = string
  description = "埋め込み用 Bedrock モデルID（knowledge_mcp / db_hiroba_qa_init）"
}

variable "embedding_vector_dim" {
  type        = number
  description = "埋め込みモデルの出力次元（ADR-0017 のパラメータ化, §6.2）"
}

# --- db_hiroba_qa_init のデータ関連（既存 .env 引き継ぎ, §5.6）---
# 注意: db_hiroba_qa_init の main.py は CSV_DATA_DIR="/" + os.environ["CSV_DATA_DIR"] と
# 先頭に "/" を付けるため、ここでは先頭スラッシュ無しの "data" を渡す（→ /data）。
# シード元データは ADR-0034 によりイメージに /data として同梱済み。
variable "csv_data_dir" {
  type    = string
  default = "data"
}

variable "qa_original_file" {
  type    = string
  default = "exportjson_withguid_small.json"
}

variable "question_altered_file" {
  type    = string
  default = "question_altered_small.csv"
}

variable "category_file" {
  type    = string
  default = "category.csv"
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
