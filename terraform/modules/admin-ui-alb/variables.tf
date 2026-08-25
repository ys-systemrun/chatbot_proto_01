variable "name_prefix" {
  type        = string
  description = "リソース名の接頭辞（例: chatbot-invitro）"
}

variable "vpc_id" {
  type        = string
  description = "ターゲットグループを作成する VPC の ID（既存 VPC, ADR-0036）"
}

variable "public_subnet_ids" {
  type        = list(string)
  description = "ALB（internet-facing）を配置するパブリックサブネット ID 群（ADR-0041）"
}

variable "alb_security_group_id" {
  type        = string
  description = "ALB に関連付ける SG（network モジュールの sg-admin-ui-alb）"
}

variable "container_port" {
  type        = number
  default     = 8000
  description = "admin_ui（web_backend）コンテナポート。ターゲットグループのポート"
}

variable "allowed_cidr_blocks" {
  type        = list(string)
  description = "ALB への 80 番インバウンドを許可する社内IP（CIDR）。0章 Open Issue が解消するまで未確定"
}

variable "health_check_path" {
  type        = string
  default     = "/health"
  description = "ターゲットグループの HTTP ヘルスチェックパス（web_backend の /health, T1）"
}
