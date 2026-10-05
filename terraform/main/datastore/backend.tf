# datastore 構成の state（ADR-0097）。ナレッジデータの DVC リモート（S3 バケット）だけを持つ、
# database / app とは独立した長寿命の層。destroy-database / destroy-app の対象外で、破棄コマンドは用意しない。
#
# bootstrap（state バケット）に同居させない理由: bootstrap の state はローカルファイルで、
# state バケットが既に存在すると apply がスキップされる（ensure_state_bucket）。後から追加した
# リソースを別マシンからも冪等に apply できるよう、S3 バックエンドの独立した state にする。
#
# bucket / key / region は terraform init の -backend-config で注入する（実値は Git 管理外, ADR-0038）:
#   -backend-config="key=datastore/state.tfstate"

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }

  backend "s3" {
    # bucket / key / region は -backend-config で注入（実値は Git 管理外）
    encrypt = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project = "chatbot_invitro"
      Env     = "verify"
      Layer   = "datastore"
      Managed = "terraform"
    }
  }
}
