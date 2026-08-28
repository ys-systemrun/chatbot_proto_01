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

resource "aws_security_group" "agent_invitro" {
  name        = "${var.name_prefix}-sg-agent-invitro"
  description = "agent_invitro: outbound only (ADR-0025)"
  vpc_id      = data.aws_vpc.this.id
  tags        = { Name = "${var.name_prefix}-sg-agent-invitro" }
}

resource "aws_security_group" "tag_selector_mcp" {
  name        = "${var.name_prefix}-sg-tag-selector-mcp"
  description = "tag_selector_mcp: inbound from agent_invitro / verification only"
  vpc_id      = data.aws_vpc.this.id
  tags        = { Name = "${var.name_prefix}-sg-tag-selector-mcp" }
}

resource "aws_security_group" "knowledge_mcp" {
  name        = "${var.name_prefix}-sg-knowledge-mcp"
  description = "knowledge_mcp: inbound from agent_invitro / verification only"
  vpc_id      = data.aws_vpc.this.id
  tags        = { Name = "${var.name_prefix}-sg-knowledge-mcp" }
}

resource "aws_security_group" "rds" {
  name        = "${var.name_prefix}-sg-rds"
  description = "RDS: inbound 5432 from knowledge_mcp / verification (db_hiroba_qa_init) only"
  vpc_id      = data.aws_vpc.this.id
  tags        = { Name = "${var.name_prefix}-sg-rds" }
}

# db_hiroba_qa_init と mcp-inspector-task が共用（§5.1）
resource "aws_security_group" "verification_task" {
  name        = "${var.name_prefix}-sg-verification-task"
  description = "db_hiroba_qa_init / MCP Inspector verification task"
  vpc_id      = data.aws_vpc.this.id
  tags        = { Name = "${var.name_prefix}-sg-verification-task" }
}

# admin_ui（管理UI, ADR-0041）: インターネット向け ALB 用 SG。
# 社内IP（CIDR）からの 80 番インバウンド許可ルールは app 構成の admin-ui-alb モジュールで付与する
# （許可 CIDR は app 構成の変数, IMPL-202608211050 T15/5.4）。ここでは SG 本体と
# 「ALB → admin_ui タスク（コンテナポート）」のegressのみを定義する。
resource "aws_security_group" "admin_ui_alb" {
  name        = "${var.name_prefix}-sg-admin-ui-alb"
  description = "admin_ui ALB: inbound 80 from office CIDR (rule added in app), outbound to admin_ui task only"
  vpc_id      = data.aws_vpc.this.id
  tags        = { Name = "${var.name_prefix}-sg-admin-ui-alb" }
}

# admin_ui タスク用 SG。インバウンドは ALB SG からのコンテナポートのみ許可（ADR-0041）。
resource "aws_security_group" "admin_ui_task" {
  name        = "${var.name_prefix}-sg-admin-ui-task"
  description = "admin_ui task: inbound from ALB SG (container port) only"
  vpc_id      = data.aws_vpc.this.id
  tags        = { Name = "${var.name_prefix}-sg-admin-ui-task" }
}

# VPC エンドポイント用（443 を VPC 内タスクから受ける）
resource "aws_security_group" "vpc_endpoints" {
  name        = "${var.name_prefix}-sg-vpce"
  description = "VPC interface endpoints (ECR/Logs/Secrets/Bedrock): 443 from VPC"
  vpc_id      = data.aws_vpc.this.id
  tags        = { Name = "${var.name_prefix}-sg-vpce" }
}

# --- インバウンド許可ルール（表の From→To）---

# agent_invitro -> tag_selector_mcp (8200)
resource "aws_vpc_security_group_ingress_rule" "tag_from_agent" {
  security_group_id            = aws_security_group.tag_selector_mcp.id
  referenced_security_group_id = aws_security_group.agent_invitro.id
  from_port                    = var.tag_selector_mcp_port
  to_port                      = var.tag_selector_mcp_port
  ip_protocol                  = "tcp"
  description                  = "select_tags call"
}

# verification -> tag_selector_mcp (8200) : MCP Inspector（ADR-0029）
resource "aws_vpc_security_group_ingress_rule" "tag_from_verification" {
  security_group_id            = aws_security_group.tag_selector_mcp.id
  referenced_security_group_id = aws_security_group.verification_task.id
  from_port                    = var.tag_selector_mcp_port
  to_port                      = var.tag_selector_mcp_port
  ip_protocol                  = "tcp"
  description                  = "MCP Inspector to tag_selector_mcp"
}

# agent_invitro -> knowledge_mcp (8100)
resource "aws_vpc_security_group_ingress_rule" "knowledge_from_agent" {
  security_group_id            = aws_security_group.knowledge_mcp.id
  referenced_security_group_id = aws_security_group.agent_invitro.id
  from_port                    = var.knowledge_mcp_port
  to_port                      = var.knowledge_mcp_port
  ip_protocol                  = "tcp"
  description                  = "search_knowledge call"
}

# verification -> knowledge_mcp (8100) : MCP Inspector
resource "aws_vpc_security_group_ingress_rule" "knowledge_from_verification" {
  security_group_id            = aws_security_group.knowledge_mcp.id
  referenced_security_group_id = aws_security_group.verification_task.id
  from_port                    = var.knowledge_mcp_port
  to_port                      = var.knowledge_mcp_port
  ip_protocol                  = "tcp"
  description                  = "MCP Inspector to knowledge_mcp"
}

# admin_ui ALB -> admin_ui task (container port) : ADR-0041（ALB 配下のタスクは ALB からのみ受ける）
resource "aws_vpc_security_group_ingress_rule" "admin_ui_task_from_alb" {
  security_group_id            = aws_security_group.admin_ui_task.id
  referenced_security_group_id = aws_security_group.admin_ui_alb.id
  from_port                    = var.admin_ui_port
  to_port                      = var.admin_ui_port
  ip_protocol                  = "tcp"
  description                  = "ALB to admin_ui container"
}

# admin_ui task -> knowledge_mcp (8100) : agent_invitro→knowledge_mcp と同一形式（IMPL-202608211050 T10）
resource "aws_vpc_security_group_ingress_rule" "knowledge_from_admin_ui" {
  security_group_id            = aws_security_group.knowledge_mcp.id
  referenced_security_group_id = aws_security_group.admin_ui_task.id
  from_port                    = var.knowledge_mcp_port
  to_port                      = var.knowledge_mcp_port
  ip_protocol                  = "tcp"
  description                  = "admin_ui to knowledge_mcp (QA/tag management via MCP)"
}

# admin_ui task -> tag_selector_mcp (8200) : 検証機能（select_tags 呼び出し, ADR-0049 / IMPL-202608260909 T18）。
# knowledge_from_admin_ui と同一形式。既存の verification -> tag_selector_mcp（MCP Inspector, ADR-0029）
# とは別概念のため、名称・コメントに verification を用いず tag_selector_from_admin_ui とする。
resource "aws_vpc_security_group_ingress_rule" "tag_selector_from_admin_ui" {
  security_group_id            = aws_security_group.tag_selector_mcp.id
  referenced_security_group_id = aws_security_group.admin_ui_task.id
  from_port                    = var.tag_selector_mcp_port
  to_port                      = var.tag_selector_mcp_port
  ip_protocol                  = "tcp"
  description                  = "admin_ui to tag_selector_mcp (verification feature select_tags)"
}

# admin_ui task -> agent_invitro (8300) : /ask-sl 中継（ADR-0045 / IMPL-202608241104 T23）。
# knowledge_from_admin_ui と同一形式。agent_invitro は ALB からは到達不可のまま（ADR-0023）。
resource "aws_vpc_security_group_ingress_rule" "agent_invitro_from_admin_ui" {
  security_group_id            = aws_security_group.agent_invitro.id
  referenced_security_group_id = aws_security_group.admin_ui_task.id
  from_port                    = var.agent_invitro_port
  to_port                      = var.agent_invitro_port
  ip_protocol                  = "tcp"
  description                  = "admin_ui to agent_invitro (/ask-sl relay)"
}

# admin_ui task -> rds (5432) : 会話評価（conversation データベース）用（ADR-0045 / IMPL-202608241104 T24）。
# rds_from_knowledge 等と同一形式。到達は許可するが、注入される資格情報は conversation データベース用
# のみに限定することで chatbot データベースへのアクセスを防ぐ（ADR-0045 の資格情報スコープ）。
resource "aws_vpc_security_group_ingress_rule" "rds_from_admin_ui" {
  security_group_id            = aws_security_group.rds.id
  referenced_security_group_id = aws_security_group.admin_ui_task.id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
  description                  = "admin_ui conversation evaluation (conversation database)"
}

# knowledge_mcp -> rds (5432)
resource "aws_vpc_security_group_ingress_rule" "rds_from_knowledge" {
  security_group_id            = aws_security_group.rds.id
  referenced_security_group_id = aws_security_group.knowledge_mcp.id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
  description                  = "knowledge_mcp query"
}

# tag_selector_mcp -> rds (5432): タグ台帳(正本)を DB から読み込む（ADR-0008）
resource "aws_vpc_security_group_ingress_rule" "rds_from_tag_selector" {
  security_group_id            = aws_security_group.rds.id
  referenced_security_group_id = aws_security_group.tag_selector_mcp.id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
  description                  = "tag_selector_mcp taxonomy read"
}

# verification (db_hiroba_qa_init) -> rds (5432)（ADR-0030）
resource "aws_vpc_security_group_ingress_rule" "rds_from_verification" {
  security_group_id            = aws_security_group.rds.id
  referenced_security_group_id = aws_security_group.verification_task.id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
  description                  = "db_hiroba_qa_init migration/seed"
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
    agent_invitro     = aws_security_group.agent_invitro.id
    tag_selector_mcp  = aws_security_group.tag_selector_mcp.id
    knowledge_mcp     = aws_security_group.knowledge_mcp.id
    verification_task = aws_security_group.verification_task.id
    vpc_endpoints     = aws_security_group.vpc_endpoints.id
    # admin_ui タスクは knowledge_mcp / VPCエンドポイント等へ出る（到達可否は相手側 ingress で制御）。
    admin_ui_task = aws_security_group.admin_ui_task.id
  }
}

resource "aws_vpc_security_group_egress_rule" "all" {
  for_each          = local.egress_sgs
  security_group_id = each.value
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
  description       = "allow all outbound"
}

# ALB SG のアウトバウンドは admin_ui タスク宛のコンテナポートのみに限定する（ADR-0041, 5.1節）。
resource "aws_vpc_security_group_egress_rule" "admin_ui_alb_to_task" {
  security_group_id            = aws_security_group.admin_ui_alb.id
  referenced_security_group_id = aws_security_group.admin_ui_task.id
  from_port                    = var.admin_ui_port
  to_port                      = var.admin_ui_port
  ip_protocol                  = "tcp"
  description                  = "ALB to admin_ui container only"
}

# ===========================================================================
# VPC エンドポイント（NAT なしで ECR pull / Logs / Secrets / Bedrock 到達）
# ADR-0036: 既存 VPC 側に用意がある場合は create_vpc_endpoints=false で抑止。
# ===========================================================================

locals {
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
  subnet_ids          = var.private_subnet_ids
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  private_dns_enabled = true
  tags                = { Name = "${var.name_prefix}-vpce-${each.value}" }
}
