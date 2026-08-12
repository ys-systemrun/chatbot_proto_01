# ecr モジュール（IMPL-202608101542 §5.2, ADR-0030）
# 4コンポーネント + 検証用 MCP Inspector イメージ用のリポジトリを作成。
# push 時脆弱性スキャンを有効化（推奨）。

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

variable "repository_names" {
  type        = list(string)
  description = "作成する ECR リポジトリ名のリスト"
}

variable "image_tag_mutability" {
  type    = string
  default = "MUTABLE"
}

resource "aws_ecr_repository" "this" {
  for_each             = toset(var.repository_names)
  name                 = each.value
  image_tag_mutability = var.image_tag_mutability
  force_delete         = true # 検証用途: destroy でイメージごと削除できるように

  image_scanning_configuration {
    scan_on_push = true
  }
}

output "repository_urls" {
  description = "リポジトリ名 -> URI のマップ"
  value       = { for k, r in aws_ecr_repository.this : k => r.repository_url }
}

output "repository_arns" {
  value = { for k, r in aws_ecr_repository.this : k => r.arn }
}
