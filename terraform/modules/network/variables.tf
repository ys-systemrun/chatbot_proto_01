variable "name_prefix" {
  type        = string
  description = "リソース名の接頭辞（例: chatbot-verify）"
}

# ADR-0036: VPC・プライベートサブネットは新規作成せず、既存リソースを ID で参照する。
variable "vpc_id" {
  type        = string
  description = "既存 VPC の ID（基盤チーム/別プロジェクトが管理, ADR-0036）"
}

variable "private_subnet_ids" {
  type        = list(string)
  description = "既存プライベートサブネットの ID 群（2つ以上, DBサブネットグループ要件 ADR-0026）"
}

variable "knowledge_mcp_port" {
  type    = number
  default = 8100
}

variable "tag_selector_mcp_port" {
  type    = number
  default = 8200
}

# ADR-0036: 既存 VPC 側に同等のエンドポイントが既にある場合は false にして本構成での作成を抑止する。
variable "create_vpc_endpoints" {
  type        = bool
  default     = true
  description = "S3 ゲートウェイ + Interface 型 VPC エンドポイントを本構成で作成するか"
}
