# ecs-app-task モジュール（ADR-0095）
# 常駐4サービス（tag_selector_mcp / knowledge_mcp / agent_invitro / admin_ui）を 1 タスク・複数コンテナで
# 動かす。イメージはコンテナごとに別（ECR リポジトリも従来どおり）。同一タスク内はネットワーク名前空間を
# 共有するため、相互通信は localhost:<port> で行い Service Connect は使わない。
# 旧 ecs-service モジュール（サービスごとに1タスク, ADR-0024/0025）を置き換える。

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

locals {
  container_defs = [
    for name, c in var.containers : merge(
      {
        name      = name
        image     = c.image
        essential = true # ADR-0095 決定1: 1つでも停止したらタスクごと再起動させる

        portMappings = [{
          containerPort = c.port
          protocol      = "tcp"
        }]

        environment = [for k, v in c.environment : { name = k, value = v }]
        secrets     = [for k, v in c.secrets : { name = k, valueFrom = v }]

        logConfiguration = {
          logDriver = "awslogs"
          options = {
            "awslogs-group"         = aws_cloudwatch_log_group.this[name].name
            "awslogs-region"        = var.region
            "awslogs-stream-prefix" = name
          }
        }
      },
      c.command != null ? { command = c.command } : {},
      c.health_check_command != null ? {
        healthCheck = {
          command     = c.health_check_command
          interval    = 15
          timeout     = 5
          retries     = 5
          startPeriod = 60
        }
      } : {},
      length(c.depends_on_healthy) > 0 ? {
        dependsOn = [for d in c.depends_on_healthy : { containerName = d, condition = "HEALTHY" }]
      } : {},
    )
  ]

  # execution ロールが GetSecretValue できる必要がある Secrets（全コンテナの和集合）。
  all_secret_arns = distinct(flatten([for c in var.containers : values(c.secrets)]))
}

# ロググループはコンテナ単位（/ecs/<コンテナ名>）。旧構成（サービス単位）と同じ名前にそろえる。
resource "aws_cloudwatch_log_group" "this" {
  for_each          = var.containers
  name              = "/ecs/${each.key}"
  retention_in_days = var.log_retention_days
}

resource "aws_ecs_task_definition" "this" {
  family                   = var.name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.cpu
  memory                   = var.memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode(local.container_defs)

  lifecycle {
    precondition {
      condition = alltrue([
        for c in var.containers : alltrue([
          for d in c.depends_on_healthy :
          contains(keys(var.containers), d) && var.containers[d].health_check_command != null
        ])
      ])
      error_message = "depends_on_healthy の相手は containers に存在し、health_check_command を持つ必要があります。"
    }
  }
}

resource "aws_ecs_service" "this" {
  name                   = var.name
  cluster                = var.cluster_arn
  task_definition        = aws_ecs_task_definition.this.arn
  desired_count          = var.desired_count
  launch_type            = "FARGATE"
  enable_execute_command = var.enable_execute_command

  # ALB 配下のときだけ、起動直後の /health 失敗で切られないよう猶予を置く。
  health_check_grace_period_seconds = var.target_group_arn != null ? var.health_check_grace_period_seconds : null

  network_configuration {
    subnets          = var.subnet_ids
    security_groups  = var.security_group_ids
    assign_public_ip = false # ADR-0041: タスク自体は非公開（ALB のみ公開）
  }

  dynamic "load_balancer" {
    for_each = var.target_group_arn != null ? [1] : []
    content {
      target_group_arn = var.target_group_arn
      container_name   = var.target_container_name
      container_port   = var.containers[var.target_container_name].port
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
