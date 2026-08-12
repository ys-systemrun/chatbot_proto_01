# cost-alert モジュール — Amazon Bedrock の月額コスト予算アラート。
# AWS Budgets（無料）で Service=Amazon Bedrock を絞り、しきい値超過時にメール通知する。
# 注意: Bedrock 利用料はリソースタグで按分できないため、Service ディメンションで絞る。
#       この環境専用アカウントなら Service=Bedrock がそのまま本環境の Bedrock 費用。

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

variable "name" {
  type = string
}

variable "monthly_limit_usd" {
  type        = number
  description = "月額予算（USD）。実額80% / 予測100% でアラート。"
}

variable "alert_emails" {
  type        = list(string)
  description = "通知先メールアドレス（1件以上）"
}

resource "aws_budgets_budget" "bedrock" {
  name         = var.name
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_limit_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_filter {
    name   = "Service"
    values = ["Amazon Bedrock"]
  }

  # 実額が予算の80%を超えたら通知
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = var.alert_emails
  }

  # 月末予測が予算の100%を超える見込みになったら通知
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = var.alert_emails
  }
}

output "budget_name" {
  value = aws_budgets_budget.bedrock.name
}
