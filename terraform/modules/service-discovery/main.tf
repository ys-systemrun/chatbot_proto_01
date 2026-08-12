# service-discovery モジュール（IMPL-202608101542 §5.5 / 要件定義書6.2節）
# ECS Service Connect 用の Cloud Map HTTP 名前空間。
# docker-compose の内部 DNS（サービス名解決）に相当する。

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

variable "namespace_name" {
  type        = string
  description = "Service Connect 名前空間（例: chatbot.internal）"
}

resource "aws_service_discovery_http_namespace" "this" {
  name        = var.namespace_name
  description = "chatbot_invitro Service Connect namespace"
}

output "namespace_arn" {
  value = aws_service_discovery_http_namespace.this.arn
}

output "namespace_name" {
  value = aws_service_discovery_http_namespace.this.name
}
