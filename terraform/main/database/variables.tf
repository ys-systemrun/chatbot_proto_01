# database 構成の変数（ADR-0039 §5.1）。
#
# ADR-0038/0040: 全変数は terraform/.env（AWS_REGION / AWS_ACCOUNT_ID / NAME_PREFIX / STATE_BUCKET
# と TF_VAR_*）に一元化し、deploy（コンテナ内 Python）が TF_VAR_* 環境変数として供給する。
# 手動 apply する場合は `deploy shell`（環境設定済みのコンテナ内 bash）から実行する。

# --- 共通値（ADR-0038, .env の TF_VAR_* から供給）---
variable "aws_region" {
  type        = string
  description = "デプロイ先リージョン（provider / 各タスク定義の awslogs-region に使用）"
}

# database 構成自身の .tf では消費しないが、ADR-0038 の共通値供給を app 構成とそろえるために宣言する
# （安全ガードで使う AWS_ACCOUNT_ID とは別。未設定でも既定 "" のままでよい）。
variable "aws_account_id" {
  type        = string
  default     = ""
  description = "デプロイ先 AWS アカウントID（ADR-0038 共通値。database 構成では未使用）"
}

variable "name_prefix" {
  type    = string
  default = "chatbot-verify"
}

# database 構成は terraform_remote_state を使わない（app 構成からの片方向参照のみ, ADR-0039）。
# state_bucket は本構成では消費しないが、ADR-0038 の共通値供給を app 構成とそろえるために宣言する。
variable "state_bucket" {
  type        = string
  default     = ""
  description = "Terraform state を保管する S3 バケット名（ADR-0038 共通値。database 構成では未使用）"
}

# --- ネットワーク基盤（旧 verify-network, ADR-0036）---
# ADR-0036: 既存 VPC・サブネットを ID で参照する（基盤チーム/別プロジェクト管理）。
variable "vpc_id" {
  type        = string
  description = "既存 VPC の ID"
}

variable "private_subnet_ids" {
  type        = list(string)
  description = "既存プライベートサブネットの ID 群（2つ以上, ADR-0026）"
}

# IMPL-202608211050 T9 / ADR-0041: admin_ui の ALB（internet-facing）を配置する既存
# パブリックサブネット。SG（sg-admin-ui-alb/task）は network モジュールで作成し、app 構成が
# local.db 経由で参照する。0章 Open Issue #2 が解消するまで値未確定（既定 [] で apply 阻害しない）。
variable "public_subnet_ids" {
  type        = list(string)
  default     = []
  description = "既存 VPC のパブリックサブネット ID 群（admin_ui の ALB 配置用, ADR-0041）"
}

variable "admin_ui_port" {
  type        = number
  default     = 8000
  description = "admin_ui（web_backend）のコンテナポート"
}

# 会話評価用データベース名（ADR-0044 / IMPL-202608241104 T20, T29）。db_hiroba_qa_init の
# CONVERSATION_DB_NAME・database モジュールの接続 URL シークレット両方で使う。
variable "conversation_db_name" {
  type        = string
  default     = "conversation"
  description = "会話評価用データベース名（同一 RDS 上に別データベースとして作成）"
}

variable "create_vpc_endpoints" {
  type        = bool
  default     = true
  description = "既存 VPC 側にエンドポイントが無い場合 true（ある場合は false で抑止, ADR-0036）"
}

# --- RDS（旧 verify-database, §5.3, 実装時に確定）---
variable "rds_engine_version" {
  type        = string
  description = "pgvector 対応の PostgreSQL バージョン（AWS 公式で要確認, §10）"
}

variable "rds_instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "multi_az" {
  type    = bool
  default = false
}

# ADR-0037: DB を永続化運用するため、既定で削除保護を有効化。
# 明示破棄時は destroy-database が -var deletion_protection=false -var skip_final_snapshot=true で destroy する。
variable "deletion_protection" {
  type    = bool
  default = true
}

variable "skip_final_snapshot" {
  type    = bool
  default = true
}

# --- シード用イメージ（db-hiroba-qa-init）---
variable "image_tag" {
  type    = string
  default = "latest"
}

# --- db_hiroba_qa_init のデータ・埋め込み関連（旧 verify から移設, §5.6）---
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

# 埋め込み（ADR-0031, モデルIDは実装時に確定）。db_hiroba_qa_init のシード計算で使用。
variable "bedrock_embedding_model_id" {
  type        = string
  description = "埋め込み用 Bedrock モデルID（db_hiroba_qa_init のシード計算）"
}

variable "embedding_vector_dim" {
  type        = number
  description = "埋め込みモデルの出力次元（ADR-0017 のパラメータ化, §6.2）"
}
