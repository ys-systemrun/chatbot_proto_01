# app 構成の state（ADR-0039）。アプリ側 ECS 常駐サービス周辺リソース。
#
# backend ブロックは変数を参照できない（§10）。bucket / key / region はいずれもここに直書きせず、
# terraform init の -backend-config で注入する（実値は Git 管理外, ADR-0038）:
#   terraform init -reconfigure `
#     -backend-config="bucket=<state-bucket>" `
#     -backend-config="region=<region>" `
#     -backend-config="key=app/state.tfstate" `
#     -backend-config="use_lockfile=true"
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
    # bucket / key / region は -backend-config で注入（実値は Git 管理外）
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
      Layer   = "app"
      Managed = "terraform"
    }
  }
}
