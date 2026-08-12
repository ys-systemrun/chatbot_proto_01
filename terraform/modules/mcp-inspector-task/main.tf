# mcp-inspector-task モジュール（IMPL-202608101542 §5.7, ADR-0029）
# MCP Inspector（Node.js CLI）を入れた検証専用イメージのタスク定義のみ。
# 常駐サービスは作らず、必要時に `aws ecs run-task` + ECS Exec で使う（§8.2）。

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

variable "family" {
  type    = string
  default = "mcp-inspector"
}

variable "region" {
  type = string
}

variable "image_uri" {
  type        = string
  description = "MCP Inspector 検証用イメージ URI（既存4コンポーネントとは別の新規イメージ）"
}

variable "cpu" {
  type    = number
  default = 512
}

variable "memory" {
  type    = number
  default = 1024
}

variable "log_retention_days" {
  type    = number
  default = 14
}

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "execution" {
  name               = "${var.family}-exec"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

resource "aws_iam_role_policy_attachment" "execution_managed" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "task" {
  name               = "${var.family}-task"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

# ECS Exec 必須（§8.2, §10: 事後有効化不可）
resource "aws_iam_role_policy" "task_exec_command" {
  name = "${var.family}-ssmmessages"
  role = aws_iam_role.task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "ssmmessages:CreateControlChannel",
        "ssmmessages:CreateDataChannel",
        "ssmmessages:OpenControlChannel",
        "ssmmessages:OpenDataChannel",
      ]
      Resource = "*"
    }]
  })
}

resource "aws_cloudwatch_log_group" "this" {
  name              = "/ecs/${var.family}"
  retention_in_days = var.log_retention_days
}

resource "aws_ecs_task_definition" "this" {
  family                   = var.family
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.cpu
  memory                   = var.memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([{
    name      = var.family
    image     = var.image_uri
    essential = true
    # メインプロセスが終了しないよう保持（ECS Exec で接続して使う）
    command = ["sleep", "infinity"]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.this.name
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = var.family
      }
    }
  }])
}

output "task_definition_arn" {
  value = aws_ecs_task_definition.this.arn
}

output "family" {
  value = aws_ecs_task_definition.this.family
}
