# Phase 0 ブートストラップ（ADR-0027, IMPL-202608101542 §4/§7.1）
# メイン構成（envs/verify）の Terraform state を保管する S3 バケットを、
# メイン構成とは別に管理する。循環依存回避のため（§10）、これを先に apply する。
#
# 使い方:
#   cd terraform/bootstrap
#   terraform init
#   terraform apply -var="aws_region=<region>" -var="state_bucket_name=<globally-unique-name>"
# 出力された bucket 名を envs/verify/backend.tf に設定する。

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source = "hashicorp/aws"
      # account-regional 名前空間（bucket_namespace = "account-regional"）は
      # AWS プロバイダ 6.37.0 以降で対応（state_bucket_name の "-an" サフィックスに必須）。
      version = ">= 6.37"
    }
  }
  # bootstrap 自体の state はローカル（このバケットを作るのが目的なので S3 は使えない）。
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  type        = string
  description = "デプロイ先リージョン（発注者から受領、Open Issue #6）"
}

variable "state_bucket_name" {
  type        = string
  description = "Terraform state 用 S3 バケット名（グローバル一意）"
}

variable "create_lock_table" {
  type        = bool
  default     = false
  description = "Terraform 1.10 未満で DynamoDB ロックを使う場合 true。1.10 以上なら S3 ネイティブロック（use_lockfile）を使い false のままでよい。"
}

variable "lock_table_name" {
  type        = string
  default     = "terraform-locks"
  description = "DynamoDB ロックテーブル名（create_lock_table=true のときのみ）"
}

resource "aws_s3_bucket" "state" {
  bucket = var.state_bucket_name
  # account-regional 名前空間バケット。state_bucket_name が "-an" サフィックス
  # （{prefix}-{account-id}-{region}-an）の場合、この宣言が必須（AWS プロバイダ >= 6.37）。
  # 未指定だと "is an account-regional namespace bucket" 検証エラーになる。
  bucket_namespace = "account-regional"
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256" # SSE-S3。SSE-KMS を使う場合は aws:kms + kms_master_key_id を指定。
    }
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_dynamodb_table" "lock" {
  count        = var.create_lock_table ? 1 : 0
  name         = var.lock_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"
  attribute {
    name = "LockID"
    type = "S"
  }
}

output "state_bucket_name" {
  value = aws_s3_bucket.state.id
}

output "lock_table_name" {
  value = var.create_lock_table ? aws_dynamodb_table.lock[0].name : null
}
