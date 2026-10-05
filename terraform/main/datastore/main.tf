# ナレッジデータの DVC リモート（ADR-0097）。
#
# DVC は内容アドレス形式（files/md5/<hash>）で保存し既存オブジェクトを上書きしないため、
# 古いバージョンを消すライフサイクルルールは設けない。誤削除に備えてバージョニングを有効にし、
# terraform からの破棄も prevent_destroy で拒否する（破棄が必要なら手動で外す）。

variable "aws_region" {
  type        = string
  description = "デプロイ先リージョン（.env の AWS_REGION から供給）"
}

variable "name_prefix" {
  type    = string
  default = "chatbot-invitro"
}

data "aws_caller_identity" "current" {}

locals {
  # グローバル一意にするためアカウントID・リージョンを含める。
  # .dvc/config の remote URL（s3://<この名前>/store）と一致させること。
  dvc_bucket_name = "${var.name_prefix}-dvc-${data.aws_caller_identity.current.account_id}-${var.aws_region}"
}

resource "aws_s3_bucket" "dvc" {
  bucket = local.dvc_bucket_name

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "dvc" {
  bucket = aws_s3_bucket.dvc.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "dvc" {
  bucket = aws_s3_bucket.dvc.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256" # SSE-S3
    }
  }
}

resource "aws_s3_bucket_public_access_block" "dvc" {
  bucket                  = aws_s3_bucket.dvc.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

output "dvc_bucket_name" {
  value = aws_s3_bucket.dvc.id
}

output "dvc_remote_url" {
  description = ".dvc/config の remote URL に設定する値"
  value       = "s3://${aws_s3_bucket.dvc.id}/store"
}
