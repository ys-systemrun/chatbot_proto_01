# network モジュール（IMPL-202608101542 §5.1, ADR-0023）
# AWS 内部限定。パブリックサブネット・IGW は既定で作らない（enable_nat_gateway=true のときのみ）。
# Fargate のイメージ取得・ログ・Secrets・Bedrock 到達は Interface/Gateway VPC エンドポイントで賄う。

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

data "aws_region" "current" {}

locals {
  az_count = length(var.availability_zones)
}

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = "${var.name_prefix}-vpc" }
}

# --- プライベートサブネット（各 AZ に1つ）---
resource "aws_subnet" "private" {
  count             = local.az_count
  vpc_id            = aws_vpc.this.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, count.index)
  availability_zone = var.availability_zones[count.index]
  tags              = { Name = "${var.name_prefix}-private-${count.index}" }
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.this.id
  tags   = { Name = "${var.name_prefix}-private-rt" }
}

resource "aws_route_table_association" "private" {
  count          = local.az_count
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

# --- 任意: NAT 経路（外部 LLM API を使う場合のみ、§5.1）---
resource "aws_internet_gateway" "this" {
  count  = var.enable_nat_gateway ? 1 : 0
  vpc_id = aws_vpc.this.id
  tags   = { Name = "${var.name_prefix}-igw" }
}

resource "aws_subnet" "public" {
  count             = var.enable_nat_gateway ? local.az_count : 0
  vpc_id            = aws_vpc.this.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, count.index + 100)
  availability_zone = var.availability_zones[count.index]
  tags              = { Name = "${var.name_prefix}-public-${count.index}" }
}

resource "aws_eip" "nat" {
  count  = var.enable_nat_gateway ? 1 : 0
  domain = "vpc"
}

resource "aws_nat_gateway" "this" {
  count         = var.enable_nat_gateway ? 1 : 0
  allocation_id = aws_eip.nat[0].id
  subnet_id     = aws_subnet.public[0].id
  tags          = { Name = "${var.name_prefix}-nat" }
  depends_on    = [aws_internet_gateway.this]
}

resource "aws_route_table" "public" {
  count  = var.enable_nat_gateway ? 1 : 0
  vpc_id = aws_vpc.this.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this[0].id
  }
}

resource "aws_route_table_association" "public" {
  count          = var.enable_nat_gateway ? local.az_count : 0
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public[0].id
}

resource "aws_route" "private_nat" {
  count                  = var.enable_nat_gateway ? 1 : 0
  route_table_id         = aws_route_table.private.id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.this[0].id
}

# ===========================================================================
# セキュリティグループ（§5.1 の許可ルール表）
# ===========================================================================

resource "aws_security_group" "agent_invitro" {
  name        = "${var.name_prefix}-sg-agent-invitro"
  description = "agent_invitro: outbound only (ADR-0025)"
  vpc_id      = aws_vpc.this.id
  tags        = { Name = "${var.name_prefix}-sg-agent-invitro" }
}

resource "aws_security_group" "tag_selector_mcp" {
  name        = "${var.name_prefix}-sg-tag-selector-mcp"
  description = "tag_selector_mcp: inbound from agent_invitro / verification only"
  vpc_id      = aws_vpc.this.id
  tags        = { Name = "${var.name_prefix}-sg-tag-selector-mcp" }
}

resource "aws_security_group" "knowledge_mcp" {
  name        = "${var.name_prefix}-sg-knowledge-mcp"
  description = "knowledge_mcp: inbound from agent_invitro / verification only"
  vpc_id      = aws_vpc.this.id
  tags        = { Name = "${var.name_prefix}-sg-knowledge-mcp" }
}

resource "aws_security_group" "rds" {
  name        = "${var.name_prefix}-sg-rds"
  description = "RDS: inbound 5432 from knowledge_mcp / verification (db_hiroba_qa_init) only"
  vpc_id      = aws_vpc.this.id
  tags        = { Name = "${var.name_prefix}-sg-rds" }
}

# db_hiroba_qa_init と mcp-inspector-task が共用（§5.1）
resource "aws_security_group" "verification_task" {
  name        = "${var.name_prefix}-sg-verification-task"
  description = "db_hiroba_qa_init / MCP Inspector verification task"
  vpc_id      = aws_vpc.this.id
  tags        = { Name = "${var.name_prefix}-sg-verification-task" }
}

# VPC エンドポイント用（443 を VPC 内タスクから受ける）
resource "aws_security_group" "vpc_endpoints" {
  name        = "${var.name_prefix}-sg-vpce"
  description = "VPC interface endpoints (ECR/Logs/Secrets/Bedrock): 443 from VPC"
  vpc_id      = aws_vpc.this.id
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
  description                  = "MCP Inspector -> tag_selector_mcp"
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
  description                  = "MCP Inspector -> knowledge_mcp"
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
  cidr_ipv4         = var.vpc_cidr
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
  }
}

resource "aws_vpc_security_group_egress_rule" "all" {
  for_each          = local.egress_sgs
  security_group_id = each.value
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
  description       = "allow all outbound"
}

# ===========================================================================
# VPC エンドポイント（NAT なしで ECR pull / Logs / Secrets / Bedrock 到達）
# ===========================================================================

# S3 ゲートウェイ型（ECR レイヤ取得に必須）
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.this.id
  service_name      = "com.amazonaws.${data.aws_region.current.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id]
  tags              = { Name = "${var.name_prefix}-vpce-s3" }
}

locals {
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

resource "aws_vpc_endpoint" "interface" {
  for_each            = toset(local.interface_endpoints)
  vpc_id              = aws_vpc.this.id
  service_name        = "com.amazonaws.${data.aws_region.current.region}.${each.value}"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.private[*].id
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  private_dns_enabled = true
  tags                = { Name = "${var.name_prefix}-vpce-${each.value}" }
}
