variable "name" {
  type        = string
  description = "ECS サービス名・タスク定義 family・IAM ロール名の接頭辞（例: chatbot-invitro-app）"
}

variable "cluster_arn" {
  type = string
}

variable "region" {
  type = string
}

# ADR-0095: 4コンテナ合計のタスクサイズ。Fargate の有効な組み合わせ（1 vCPU なら 2〜8 GB）で指定する。
variable "cpu" {
  type    = number
  default = 1024
}

variable "memory" {
  type    = number
  default = 2048
}

# 同一タスクに並べるコンテナ群（キー＝コンテナ名。ロググループ /ecs/<キー> にも使う）。
# - port:                 コンテナポート（同一タスク内で重複不可。相互通信は localhost:<port>）
# - secrets:              環境変数名 -> Secrets Manager/SSM の valueFrom ARN（コンテナ単位で注入, ADR-0045）
# - health_check_command: コンテナヘルスチェック。depends_on_healthy で待たれる側は必須
# - depends_on_healthy:   HEALTHY になるまで起動を待つ相手のコンテナ名（起動順序, ADR-0095 決定2）
variable "containers" {
  type = map(object({
    image                = string
    port                 = number
    command              = optional(list(string))
    environment          = optional(map(string), {})
    secrets              = optional(map(string), {})
    health_check_command = optional(list(string))
    depends_on_healthy   = optional(list(string), [])
  }))
}

variable "security_group_ids" {
  type = list(string)
}

variable "subnet_ids" {
  type = list(string)
}

variable "desired_count" {
  type    = number
  default = 1
}

variable "enable_execute_command" {
  type        = bool
  default     = true
  description = "ECS Exec（ADR-0025）。execute-command は --container <名前> でコンテナを選ぶ"
}

variable "enable_bedrock" {
  type        = bool
  default     = false
  description = "タスクロールに bedrock:InvokeModel を付与（ADR-0031）。タスク内の全コンテナに効く"
}

variable "log_retention_days" {
  type    = number
  default = 14
}

# ALB 配下にするコンテナ（admin_ui, ADR-0041）。target_group_arn が null なら load_balancer を付けない。
variable "target_group_arn" {
  type    = string
  default = null
}

variable "target_container_name" {
  type        = string
  default     = null
  description = "ALB ターゲットにするコンテナ名（containers のキー）"
}

variable "health_check_grace_period_seconds" {
  type        = number
  default     = 180
  description = "ALB 配下時の猶予。dependsOn で admin_ui の起動が MCP の HEALTHY 待ちになる分を見込む"
}
