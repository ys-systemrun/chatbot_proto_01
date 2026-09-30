# ecs-app-task モジュールの IAM（実行ロール / タスクロール）
# ADR-0095 決定5: タスクが1つになったため、ロールも1組。Secrets の注入先はコンテナ定義側で限定する。

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# --- 実行ロール（イメージ pull / ログ / secrets 注入）---
resource "aws_iam_role" "execution" {
  name               = "${var.name}-exec"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

resource "aws_iam_role_policy_attachment" "execution_managed" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# secrets 注入用（全コンテナの secrets の和集合）
resource "aws_iam_role_policy" "execution_secrets" {
  count = length(local.all_secret_arns) > 0 ? 1 : 0
  name  = "${var.name}-exec-secrets"
  role  = aws_iam_role.execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue", "ssm:GetParameters"]
      Resource = local.all_secret_arns
    }]
  })
}

# --- タスクロール（アプリ実行時の権限）---
resource "aws_iam_role" "task" {
  name               = "${var.name}-task"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

# ECS Exec に必要な SSM Messages 権限（§10: enableExecuteCommand は事後有効化不可）
resource "aws_iam_role_policy" "task_exec_command" {
  count = var.enable_execute_command ? 1 : 0
  name  = "${var.name}-ssmmessages"
  role  = aws_iam_role.task.id
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

# Bedrock 呼び出し（ADR-0031, API キー不使用）。タスク内の全コンテナに効く（ADR-0095 の受容リスク）。
resource "aws_iam_role_policy" "task_bedrock" {
  count = var.enable_bedrock ? 1 : 0
  name  = "${var.name}-bedrock"
  role  = aws_iam_role.task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
      Resource = "*"
    }]
  })
}
