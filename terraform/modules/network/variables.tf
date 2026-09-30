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

# ADR-0095: Interface VPC エンドポイント・集約 ECS タスク・run-task を置く単一サブネット。
# null のときは private_subnet_ids の先頭を使う。private_subnet_ids のいずれかを指定すること。
variable "workload_subnet_id" {
  type        = string
  default     = null
  description = "エンドポイント・ECS タスクを置く単一プライベートサブネット ID（既定: private_subnet_ids[0]）"
}

variable "knowledge_mcp_port" {
  type    = number
  default = 8100
}

variable "tag_selector_mcp_port" {
  type    = number
  default = 8200
}

# IMPL-202608211050 T8/T9: admin_ui（管理UI, ADR-0041/0042）向け。
variable "admin_ui_port" {
  type        = number
  default     = 8000
  description = "admin_ui（web_backend）のコンテナポート。ALB→集約タスクの許可に使用"
}

# ADR-0036 と同様、既存 VPC のパブリックサブネットを ID で参照する（新規作成しない）。
# ALB（internet-facing, ADR-0041）の配置に使う。0章の Open Issue #2 が解消するまで値未確定。
variable "public_subnet_ids" {
  type        = list(string)
  default     = []
  description = "既存 VPC のパブリックサブネット ID 群（admin_ui の ALB 配置用, ADR-0041）"
}

# ADR-0036: 既存 VPC 側に同等のエンドポイントが既にある場合は false にして本構成での作成を抑止する。
variable "create_vpc_endpoints" {
  type        = bool
  default     = true
  description = "S3 ゲートウェイ + Interface 型 VPC エンドポイントを本構成で作成するか"
}
