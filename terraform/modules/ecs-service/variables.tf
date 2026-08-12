variable "service_name" {
  type        = string
  description = "ECS サービス名（Service Connect 名としても使用, 例: knowledge_mcp）"
}

variable "cluster_arn" {
  type = string
}

variable "region" {
  type = string
}

variable "image_uri" {
  type = string
}

variable "cpu" {
  type    = number
  default = 512
}

variable "memory" {
  type    = number
  default = 1024
}

variable "container_port" {
  type        = number
  default     = null
  description = "外部公開ポート。agent_invitro は null（ポート無し, ADR-0025）"
}

variable "environment" {
  type        = map(string)
  default     = {}
  description = "平文環境変数（機密は secrets で）"
}

variable "secrets" {
  type        = map(string)
  default     = {}
  description = "環境変数名 -> Secrets Manager/SSM の valueFrom ARN"
}

variable "command" {
  type        = list(string)
  default     = null
  description = "コンテナ command の上書き（agent_invitro は [\"sleep\",\"infinity\"]）"
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
  description = "ECS Exec。agent_invitro は true 固定（ADR-0025）"
}

variable "enable_bedrock" {
  type        = bool
  default     = false
  description = "タスクロールに bedrock:InvokeModel を付与（ADR-0031）"
}

variable "service_connect_namespace_arn" {
  type    = string
  default = null
}

variable "service_connect_dns_name" {
  type        = string
  default     = null
  description = "Service Connect のクライアント側 DNS 名（既定は service_name）"
}

variable "health_check_command" {
  type        = list(string)
  default     = null
  description = "コンテナヘルスチェック（例: [\"CMD\",\"curl\",\"-f\",\"http://localhost:8100/health\"]）"
}

variable "log_retention_days" {
  type    = number
  default = 14
}
