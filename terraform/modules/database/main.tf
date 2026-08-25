# database モジュール（IMPL-202608101542 §5.3, ADR-0026）
# Amazon RDS for PostgreSQL（pgvector 拡張）。検証用途の最小構成。
#
# 認証情報の扱い:
#   アプリ（knowledge_mcp / db_hiroba_qa_init）は DATABASE_URL を1本の接続文字列として要求する
#   （アプリコード変更は本書スコープ外, §11）。RDS のマネージドマスターパスワード（JSON secret）は
#   URL 文字列としては注入できないため、本モジュールでは random_password を生成し、その値から
#   完全な DATABASE_URL を組み立てた独自の Secrets Manager シークレットを作成する。
#   ECS タスク定義はこのシークレット ARN を secrets 参照で注入する（§6.2, 要件6.6/6.7）。

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = ">= 3.0"
    }
  }
}

variable "name_prefix" {
  type = string
}

variable "subnet_ids" {
  type        = list(string)
  description = "DB サブネットグループに使うプライベートサブネット（§5.1）"
}

variable "security_group_id" {
  type        = string
  description = "sg-rds（§5.1）"
}

variable "engine_version" {
  type        = string
  description = "pgvector 対応の PostgreSQL バージョン。実装時に AWS 公式で再確認（§5.3, §10）"
}

variable "instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "allocated_storage" {
  type    = number
  default = 20
}

variable "db_name" {
  type    = string
  default = "chatbot"
}

# 会話評価用データベース名（ADR-0044 / IMPL-202608241104 T20）。同一 RDS インスタンス上に
# 別データベースとして作成する（db_hiroba_qa_init が CREATE DATABASE で作成, T16）。
variable "conversation_db_name" {
  type    = string
  default = "conversation"
}

variable "master_username" {
  type    = string
  default = "postgres"
}

variable "multi_az" {
  type    = bool
  default = false
}

variable "deletion_protection" {
  type    = bool
  default = false
}

# ADR-0037: DB を永続化運用する場合は false（最終スナップショット取得）にする余地を残す。
variable "skip_final_snapshot" {
  type    = bool
  default = true
}

resource "aws_db_subnet_group" "this" {
  name       = "${var.name_prefix}-db-subnet"
  subnet_ids = var.subnet_ids
}

# pgvector は shared_preload_libraries 不要。バージョンがサポートしていれば CREATE EXTENSION で有効化可能。
# rds.* の制限に備え専用パラメータグループを用意（family は engine_version に合わせて実装時に確認）。
resource "aws_db_parameter_group" "this" {
  name_prefix = "${var.name_prefix}-pg-"
  family      = "postgres${split(".", var.engine_version)[0]}"

  lifecycle {
    create_before_destroy = true
  }
}

resource "random_password" "master" {
  length  = 24
  special = false # 接続 URL に入れるため記号を避け、URL エンコード不要にする
}

resource "aws_db_instance" "this" {
  identifier     = "${var.name_prefix}-rds"
  engine         = "postgres"
  engine_version = var.engine_version
  instance_class = var.instance_class

  allocated_storage = var.allocated_storage
  storage_type      = "gp3"

  db_name  = var.db_name
  username = var.master_username
  password = random_password.master.result

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [var.security_group_id]
  parameter_group_name   = aws_db_parameter_group.this.name

  multi_az            = var.multi_az
  publicly_accessible = false
  deletion_protection = var.deletion_protection
  skip_final_snapshot = var.skip_final_snapshot
  apply_immediately   = true
}

# アプリが要求する完全な接続 URL を保持する独自シークレット。
resource "aws_secretsmanager_secret" "db_url" {
  name_prefix = "${var.name_prefix}-database-url-"
}

resource "aws_secretsmanager_secret_version" "db_url" {
  secret_id = aws_secretsmanager_secret.db_url.id
  secret_string = format(
    "postgresql://%s:%s@%s:%d/%s",
    var.master_username,
    random_password.master.result,
    aws_db_instance.this.address,
    aws_db_instance.this.port,
    var.db_name,
  )
}

output "db_url_secret_arn" {
  description = "DATABASE_URL を1本の文字列として持つシークレット ARN（ECS secrets 参照用）"
  value       = aws_secretsmanager_secret.db_url.arn
}

# conversation データベースへの接続 URL シークレット（ADR-0044 / IMPL-202608241104 T21）。
# ホスト・ポート・マスター認証情報は db_url と共通で、データベース名のみ conversation_db_name に
# 置き換える。admin_ui の CONVERSATION_DB_URL / db_hiroba_qa_init の作成・スキーマ適用で参照する。
resource "aws_secretsmanager_secret" "conversation_db_url" {
  name_prefix = "${var.name_prefix}-conversation-db-url-"
}

resource "aws_secretsmanager_secret_version" "conversation_db_url" {
  secret_id = aws_secretsmanager_secret.conversation_db_url.id
  secret_string = format(
    "postgresql://%s:%s@%s:%d/%s",
    var.master_username,
    random_password.master.result,
    aws_db_instance.this.address,
    aws_db_instance.this.port,
    var.conversation_db_name,
  )
}

output "conversation_db_url_secret_arn" {
  description = "CONVERSATION_DB_URL を1本の文字列として持つシークレット ARN（ECS secrets 参照用, ADR-0044）"
  value       = aws_secretsmanager_secret.conversation_db_url.arn
}

# ---------------------------------------------------------------------------
# エクスポート専用読み取りロール（ADR-0046 / IMPL-202608241600 T4〜T8）
# ---------------------------------------------------------------------------
# db_url（マスター権限）・conversation_db_url（マスター権限, conversation DB 向け）とは異なり、
# chatbot_export_db_url は新規ロール（マスター権限ではない）を使う。ロール自体は RDS の
# マスターパスワードではないため aws_db_instance 経由では設定できず、db_hiroba_qa_init が
# SQL の CREATE ROLE ... PASSWORD で設定する。random_password を1個生成し、(a) 生パスワード
# 専用シークレット（db_hiroba_qa_init が CREATE/ALTER ROLE に使う）と (b) 同じ値を埋め込んだ
# 完全な接続文字列シークレット（admin_ui が使う）の2つを作成する（0章）。
variable "export_reader_username" {
  type    = string
  default = "chatbot_export_reader"
}

resource "random_password" "export_reader" {
  length  = 24
  special = false # 接続 URL に入れるため記号を避け、URL エンコード不要にする
}

# db_hiroba_qa_init が CREATE ROLE / ALTER ROLE に使う生パスワード専用シークレット。
resource "aws_secretsmanager_secret" "export_reader_password" {
  name_prefix = "${var.name_prefix}-export-reader-password-"
}

resource "aws_secretsmanager_secret_version" "export_reader_password" {
  secret_id     = aws_secretsmanager_secret.export_reader_password.id
  secret_string = random_password.export_reader.result
}

output "export_reader_password_secret_arn" {
  description = "chatbot_export_reader ロールの生パスワードを持つシークレット ARN（db_init_task が参照）"
  value       = aws_secretsmanager_secret.export_reader_password.arn
}

# admin_ui が使う、chatbot_export_reader ロールでの完全な接続文字列シークレット。
resource "aws_secretsmanager_secret" "chatbot_export_db_url" {
  name_prefix = "${var.name_prefix}-chatbot-export-db-url-"
}

resource "aws_secretsmanager_secret_version" "chatbot_export_db_url" {
  secret_id = aws_secretsmanager_secret.chatbot_export_db_url.id
  secret_string = format(
    "postgresql://%s:%s@%s:%d/%s",
    var.export_reader_username,
    random_password.export_reader.result,
    aws_db_instance.this.address,
    aws_db_instance.this.port,
    var.db_name,
  )
}

output "chatbot_export_db_url_secret_arn" {
  description = "CHATBOT_EXPORT_DB_URL を1本の文字列として持つシークレット ARN（app 構成が参照, ADR-0046）"
  value       = aws_secretsmanager_secret.chatbot_export_db_url.arn
}

output "endpoint" {
  value = aws_db_instance.this.address
}

output "port" {
  value = aws_db_instance.this.port
}

output "db_name" {
  value = var.db_name
}
