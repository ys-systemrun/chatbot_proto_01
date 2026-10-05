# network モジュール（IMPL-202608101542 §5.1, ADR-0023 / ADR-0036）
# ADR-0036: VPC・プライベートサブネットは既存リソースを data source で参照する（新規作成しない）。
#           セキュリティグループと VPC エンドポイントのみを本構成で作成する。
# Fargate のイメージ取得・ログ・Secrets・Bedrock 到達は Interface/Gateway VPC エンドポイントで賄う
# （既存 VPC 側に同等の経路がある場合は create_vpc_endpoints=false）。

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

data "aws_region" "current" {}

# 既存 VPC/サブネットの参照（ADR-0036）
data "aws_vpc" "this" {
  id = var.vpc_id
}

locals {
  vpc_cidr = data.aws_vpc.this.cidr_block
}

# S3 ゲートウェイ型エンドポイント用に、既存サブネットが「使う」ルートテーブルを特定する。
# 注意: subnet_id / association.subnet-id フィルタは "明示的に関連付けられた" RT しか見つけない。
# サブネットに明示関連付けが無い場合は VPC のメインルートテーブルを暗黙利用しているため、
# 明示関連付け(aws_route_tables=複数)とメインRTの両方を取得し、locals でフォールバックする（ADR-0036）。
data "aws_route_tables" "private_explicit" {
  count  = var.create_vpc_endpoints ? 1 : 0
  vpc_id = var.vpc_id
  filter {
    name   = "association.subnet-id"
    values = var.private_subnet_ids
  }
}

data "aws_route_table" "main" {
  count  = var.create_vpc_endpoints ? 1 : 0
  vpc_id = var.vpc_id
  filter {
    name   = "association.main"
    values = ["true"]
  }
}

# ===========================================================================
# セキュリティグループ（§5.1 の許可ルール表）— 既存 VPC ID に紐づけて作成
# ===========================================================================
# ADR-0095: 常駐4サービス（tag_selector_mcp / knowledge_mcp / agent_invitro / admin_ui）は
# 1タスク（ENI 1つ）に集約したため、サービス別 SG を app_task の1つに統合した。
# 同一タスク内のコンテナ間通信は localhost で完結し SG を経由しないため、サービス間の許可ルールは無い。

# 集約タスク用 SG。インバウンドは ALB からの admin_ui ポートと、検証タスクからの MCP ポートのみ。
resource "aws_security_group" "app_task" {
  name        = "${var.name_prefix}-sg-app-task"
  description = "app task (4 containers): inbound from ALB (admin_ui) / verification (MCP) only"
  vpc_id      = data.aws_vpc.this.id
  tags        = { Name = "${var.name_prefix}-sg-app-task" }
}

resource "aws_security_group" "rds" {
  name        = "${var.name_prefix}-sg-rds"
  description = "RDS: inbound 5432 from app task / verification (db_init) only"
  vpc_id      = data.aws_vpc.this.id
  tags        = { Name = "${var.name_prefix}-sg-rds" }
}

# db_init と mcp-inspector-task が共用（§5.1）
resource "aws_security_group" "verification_task" {
  name        = "${var.name_prefix}-sg-verification-task"
  description = "db_init / MCP Inspector verification task"
  vpc_id      = data.aws_vpc.this.id
  tags        = { Name = "${var.name_prefix}-sg-verification-task" }
}

# admin_ui（管理UI, ADR-0041）: インターネット向け ALB 用 SG。
# 社内IP（CIDR）からの 80 番インバウンド許可ルールは app 構成の admin-ui-alb モジュールで付与する
# （許可 CIDR は app 構成の変数, IMPL-202608211050 T15/5.4）。ここでは SG 本体と
# 「ALB → 集約タスク（admin_ui のコンテナポート）」のegressのみを定義する。
resource "aws_security_group" "admin_ui_alb" {
  name        = "${var.name_prefix}-sg-admin-ui-alb"
  description = "admin_ui ALB: inbound 80 from office CIDR (rule added in app), outbound to app task only"
  vpc_id      = data.aws_vpc.this.id
  tags        = { Name = "${var.name_prefix}-sg-admin-ui-alb" }
}

# VPC エンドポイント用（443 を VPC 内タスクから受ける）
resource "aws_security_group" "vpc_endpoints" {
  name        = "${var.name_prefix}-sg-vpce"
  description = "VPC interface endpoints (ECR/Logs/Secrets/Bedrock): 443 from VPC"
  vpc_id      = data.aws_vpc.this.id
  tags        = { Name = "${var.name_prefix}-sg-vpce" }
}

# --- インバウンド許可ルール（表の From→To）---

# admin_ui ALB -> 集約タスクの admin_ui コンテナ : ADR-0041（ALB 配下のコンテナは ALB からのみ受ける）
resource "aws_vpc_security_group_ingress_rule" "app_task_from_alb" {
  security_group_id            = aws_security_group.app_task.id
  referenced_security_group_id = aws_security_group.admin_ui_alb.id
  from_port                    = var.admin_ui_port
  to_port                      = var.admin_ui_port
  ip_protocol                  = "tcp"
  description                  = "ALB to admin_ui container"
}

# verification -> tag_selector_mcp (8200) : MCP Inspector（ADR-0029）
resource "aws_vpc_security_group_ingress_rule" "tag_from_verification" {
  security_group_id            = aws_security_group.app_task.id
  referenced_security_group_id = aws_security_group.verification_task.id
  from_port                    = var.tag_selector_mcp_port
  to_port                      = var.tag_selector_mcp_port
  ip_protocol                  = "tcp"
  description                  = "MCP Inspector to tag_selector_mcp"
}

# verification -> knowledge_mcp (8100) : MCP Inspector
resource "aws_vpc_security_group_ingress_rule" "knowledge_from_verification" {
  security_group_id            = aws_security_group.app_task.id
  referenced_security_group_id = aws_security_group.verification_task.id
  from_port                    = var.knowledge_mcp_port
  to_port                      = var.knowledge_mcp_port
  ip_protocol                  = "tcp"
  description                  = "MCP Inspector to knowledge_mcp"
}

# 集約タスク -> rds (5432): knowledge_mcp / tag_selector_mcp（knowledge）と admin_ui（conversation・
# エクスポート）が接続する。到達は1ルールで許可するが、注入する資格情報はコンテナ単位で限定する
# （ADR-0045 / ADR-0052 の資格情報スコープ, ADR-0095 決定5）。
resource "aws_vpc_security_group_ingress_rule" "rds_from_app_task" {
  security_group_id            = aws_security_group.rds.id
  referenced_security_group_id = aws_security_group.app_task.id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
  description                  = "app task (knowledge_mcp / tag_selector_mcp / admin_ui)"
}

# verification (db_init) -> rds (5432)（ADR-0030）
resource "aws_vpc_security_group_ingress_rule" "rds_from_verification" {
  security_group_id            = aws_security_group.rds.id
  referenced_security_group_id = aws_security_group.verification_task.id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
  description                  = "db_init migration/seed"
}

# VPC エンドポイント: 443 を VPC 内から
resource "aws_vpc_security_group_ingress_rule" "vpce_from_vpc" {
  security_group_id = aws_security_group.vpc_endpoints.id
  cidr_ipv4         = local.vpc_cidr
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
  description       = "HTTPS from VPC to interface endpoints"
}

# --- アウトバウンド（すべての SG は egress 全許可。到達可否は相手側 ingress で制御）---
locals {
  egress_sgs = {
    app_task          = aws_security_group.app_task.id
    verification_task = aws_security_group.verification_task.id
    vpc_endpoints     = aws_security_group.vpc_endpoints.id
  }
}

resource "aws_vpc_security_group_egress_rule" "all" {
  for_each          = local.egress_sgs
  security_group_id = each.value
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
  description       = "allow all outbound"
}

# ALB SG のアウトバウンドは集約タスクの admin_ui コンテナポートのみに限定する（ADR-0041, 5.1節）。
resource "aws_vpc_security_group_egress_rule" "admin_ui_alb_to_task" {
  security_group_id            = aws_security_group.admin_ui_alb.id
  referenced_security_group_id = aws_security_group.app_task.id
  from_port                    = var.admin_ui_port
  to_port                      = var.admin_ui_port
  ip_protocol                  = "tcp"
  description                  = "ALB to admin_ui container only"
}

# ===========================================================================
# VPC エンドポイント（NAT なしで ECR pull / Logs / Secrets / Bedrock 到達）
# ADR-0036: 既存 VPC 側に用意がある場合は create_vpc_endpoints=false で抑止。
# ADR-0095: Interface 型は AZ（ENI）ごとに課金されるため、単一サブネット（workload_subnet_id）にだけ置く。
#           ECS タスク・run-task も同じサブネットに置き、AZ 間通信を避ける。
# ===========================================================================

locals {
  # 未指定なら private_subnet_ids の先頭を使う。private_subnet_ids（2 AZ）は RDS の
  # DB サブネットグループ用にそのまま残す（ADR-0026: 2 AZ 以上が必須）。
  workload_subnet_id = coalesce(var.workload_subnet_id, var.private_subnet_ids[0])

  explicit_route_table_ids = var.create_vpc_endpoints ? data.aws_route_tables.private_explicit[0].ids : []
  # 明示関連付けが1つも無ければ、サブネットが暗黙利用する VPC メインルートテーブルにフォールバックする。
  route_table_ids = length(local.explicit_route_table_ids) > 0 ? distinct(local.explicit_route_table_ids) : (
    var.create_vpc_endpoints ? [data.aws_route_table.main[0].route_table_id] : []
  )
  interface_endpoints = [
    "ecr.api",
    "ecr.dkr",
    "logs",
    "secretsmanager",
    "ssm",         # ECS Exec
    "ssmmessages", # ECS Exec
    "bedrock-runtime",
  ]
}

# S3 ゲートウェイ型（ECR レイヤ取得に必須）。既存サブネットのルートテーブルに関連付ける。
resource "aws_vpc_endpoint" "s3" {
  count             = var.create_vpc_endpoints ? 1 : 0
  vpc_id            = data.aws_vpc.this.id
  service_name      = "com.amazonaws.${data.aws_region.current.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = local.route_table_ids
  tags              = { Name = "${var.name_prefix}-vpce-s3" }
}

resource "aws_vpc_endpoint" "interface" {
  for_each            = var.create_vpc_endpoints ? toset(local.interface_endpoints) : toset([])
  vpc_id              = data.aws_vpc.this.id
  service_name        = "com.amazonaws.${data.aws_region.current.region}.${each.value}"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = [local.workload_subnet_id]
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  private_dns_enabled = true
  tags                = { Name = "${var.name_prefix}-vpce-${each.value}" }
}
