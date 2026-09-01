# db-init-task モジュール（IMPL-202608101542 §5.6, ADR-0030）
# db_hiroba_qa_init の ECS タスク定義のみ。常駐サービスは作らない。
# 実行は Phase 4 で `aws ecs run-task` を都度呼び出す（§8.1）。

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
  default = "db-hiroba-qa-init"
}

variable "region" {
  type = string
}

variable "image_uri" {
  type = string
}

variable "cpu" {
  type    = number
  default = 1024
}

variable "memory" {
  type    = number
  default = 2048
}

variable "environment" {
  type    = map(string)
  default = {}
}

variable "secrets" {
  type        = map(string)
  default     = {}
  description = "DATABASE_URL 等の Secrets Manager 参照"
}

variable "enable_bedrock" {
  type    = bool
  default = true # 埋め込みを Bedrock で計算（ADR-0031）
}

variable "import_bucket_arn" {
  type        = string
  default     = ""
  description = "全データインポート（ADR-0066）用 S3 バケットの ARN。enable_import_s3=true のとき権限付与に使う。"
}

variable "enable_import_s3" {
  type        = bool
  default     = false
  description = "全データインポート（ADR-0066）用の S3 権限を task role に付与するか。count 判定はプラン時に確定させる必要があるため、ARN の有無ではなく本フラグで切り替える。"
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

resource "aws_iam_role_policy" "execution_secrets" {
  count = length(var.secrets) > 0 ? 1 : 0
  name  = "${var.family}-exec-secrets"
  role  = aws_iam_role.execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue"]
      Resource = values(var.secrets)
    }]
  })
}

resource "aws_iam_role" "task" {
  name               = "${var.family}-task"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

# トラブルシュート用 ECS Exec（推奨, §5.6）
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

resource "aws_iam_role_policy" "task_bedrock" {
  count = var.enable_bedrock ? 1 : 0
  name  = "${var.family}-bedrock"
  role  = aws_iam_role.task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["bedrock:InvokeModel"]
      Resource = "*"
    }]
  })
}

# 全データインポート（ADR-0066）: IMPORT_MODE のコンテナが投入ダンプ取得（GetObject）と
# 退避バックアップ保存（PutObject）に使う。import バケットに限定して付与する（最小権限）。
resource "aws_iam_role_policy" "task_import_s3" {
  count = var.enable_import_s3 ? 1 : 0
  name  = "${var.family}-import-s3"
  role  = aws_iam_role.task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject"]
        Resource = "${var.import_bucket_arn}/*"
      },
      {
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = var.import_bucket_arn
      },
    ]
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
    name        = var.family
    image       = var.image_uri
    essential   = true
    environment = [for k, v in var.environment : { name = k, value = v }]
    secrets     = [for k, v in var.secrets : { name = k, valueFrom = v }]
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
