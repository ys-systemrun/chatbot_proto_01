# S3 バックエンド（ADR-0027）。
# bucket 名は Phase 0（terraform/bootstrap）で作成した実値に置き換える。
# バケットは Git 管理外の実値のため、初期化時に -backend-config で渡す運用でもよい:
#   terraform init \
#     -backend-config="bucket=<state-bucket>" \
#     -backend-config="region=<region>" \
#     -backend-config="key=chatbot-invitro/verify.tfstate"
#
# Terraform 1.10 以上: use_lockfile = true（S3 ネイティブロック）。
# 1.10 未満: dynamodb_table = "<lock-table>" を指定（bootstrap で create_lock_table=true）。

terraform {
  required_version = ">= 1.5.0"

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

  backend "s3" {
    key = "chatbot-invitro/verify.tfstate"
    # bucket / region は -backend-config で注入（実値は Git 管理外）
    encrypt = true
    # use_lockfile = true  # Terraform >= 1.10
    # dynamodb_table = "terraform-locks"  # Terraform < 1.10
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project = "chatbot_invitro"
      Env     = "verify"
      Managed = "terraform"
    }
  }
}
