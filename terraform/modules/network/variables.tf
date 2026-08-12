variable "name_prefix" {
  type        = string
  description = "リソース名の接頭辞（例: chatbot-verify）"
}

variable "vpc_cidr" {
  type        = string
  description = "VPC の CIDR（例: 10.20.0.0/16）"
}

variable "availability_zones" {
  type        = list(string)
  description = "プライベートサブネットを配置する AZ（2つ以上、将来の RDS Multi-AZ 化に備える）"
}

variable "knowledge_mcp_port" {
  type    = number
  default = 8100
}

variable "tag_selector_mcp_port" {
  type    = number
  default = 8200
}

variable "enable_nat_gateway" {
  type        = bool
  default     = false
  description = "外部 LLM API を使う場合のみ true。Bedrock のみなら VPC エンドポイントで代替（ADR-0023, 0031）。true にするとパブリックサブネット + IGW + NAT を作成する。"
}
