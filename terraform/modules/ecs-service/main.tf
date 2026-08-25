# ecs-service モジュール（IMPL-202608101542 §5.5, ADR-0024/0025）
# 常駐サービス共通。tag_selector_mcp / knowledge_mcp / agent_invitro で3回呼び出す。

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

locals {
  has_port = var.container_port != null
  sc_dns   = coalesce(var.service_connect_dns_name, var.service_name)
  # port_name は has_port が真のときだけ使う（portMappings / Service Connect service）。
  # container_port が null（agent_invitro 等ポート無し）でも補間エラーにならないよう null 安全にする。
  port_name = local.has_port ? "${var.service_name}-${var.container_port}" : null
  enable_sc = local.has_port && var.service_connect_namespace_arn != null

  container_def = merge(
    {
      name      = var.service_name
      image     = var.image_uri
      essential = true

      environment = [for k, v in var.environment : { name = k, value = v }]
      secrets     = [for k, v in var.secrets : { name = k, valueFrom = v }]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.this.name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = var.service_name
        }
      }
    },
    var.command != null ? { command = var.command } : {},
    local.has_port ? {
      portMappings = [{
        name          = local.port_name
        containerPort = var.container_port
        protocol      = "tcp"
      }]
    } : {},
    var.health_check_command != null ? {
      healthCheck = {
        command     = var.health_check_command
        interval    = 15
        timeout     = 5
        retries     = 5
        startPeriod = 60
      }
    } : {},
  )
}

resource "aws_cloudwatch_log_group" "this" {
  name              = "/ecs/${var.service_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_ecs_task_definition" "this" {
  family                   = var.service_name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.cpu
  memory                   = var.memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([local.container_def])
}

resource "aws_ecs_service" "this" {
  name                   = var.service_name
  cluster                = var.cluster_arn
  task_definition        = aws_ecs_task_definition.this.arn
  desired_count          = var.desired_count
  launch_type            = "FARGATE"
  enable_execute_command = var.enable_execute_command

  # ALB 配下（target_group_arn 指定時）はコンテナ起動直後の /health 失敗で切られないよう猶予を置く。
  health_check_grace_period_seconds = var.target_group_arn != null ? 60 : null

  network_configuration {
    subnets          = var.subnet_ids
    security_groups  = var.security_group_ids
    assign_public_ip = false # ADR-0041: admin_ui タスク自体は非公開（ALB のみ公開）
  }

  # ALB ターゲットグループへの接続（IMPL-202608211050 T12, admin_ui のみ）。
  # target_group_arn が null の既存3サービスにはブロックが付かない（差分なし, 5.3節）。
  dynamic "load_balancer" {
    for_each = var.target_group_arn != null ? [1] : []
    content {
      target_group_arn = var.target_group_arn
      container_name   = var.service_name
      container_port   = var.container_port
    }
  }

  dynamic "service_connect_configuration" {
    for_each = local.enable_sc ? [1] : []
    content {
      enabled   = true
      namespace = var.service_connect_namespace_arn
      service {
        port_name = local.port_name
        client_alias {
          dns_name = local.sc_dns
          port     = var.container_port
        }
      }
    }
  }

  # ポートを持たない agent_invitro でも Service Connect のクライアント側は有効化
  # （名前解決だけ使えるよう enabled=true, service ブロック無し）。
  dynamic "service_connect_configuration" {
    for_each = (!local.has_port && var.service_connect_namespace_arn != null) ? [1] : []
    content {
      enabled   = true
      namespace = var.service_connect_namespace_arn
    }
  }
}

output "task_definition_arn" {
  value = aws_ecs_task_definition.this.arn
}

output "service_name" {
  value = aws_ecs_service.this.name
}

output "task_role_arn" {
  value = aws_iam_role.task.arn
}
