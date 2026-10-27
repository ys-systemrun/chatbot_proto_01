# network モジュール（IMPL-202608101542 §5.1, ADR-0023 / ADR-0036 / ADR-0104）
# ADR-0036: VPC・プライベートサブネットは既存リソースを data source で参照する（新規作成しない）。
# ADR-0104: VPC エンドポイントは使わない。ECS タスク・run-task はパブリックサブネットに
#           パブリック IP 付きで置き、AWS サービスへはインターネットゲートウェイ経由で接続する。
# 本構成で作成するのは、集約タスク・RDS・検証タスク・ALB 用のセキュリティグループのみ。

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

# ===========================================================================
# セキュリティグループ（§5.1 の許可ルール表）— 既存 VPC ID に紐づけて作成
# ===========================================================================
# ADR-0095: 常駐4サービス（tag_selector_mcp / knowledge_mcp / agent_invitro / admin_ui）は
# 1タスク（ENI 1つ）に集約したため、サービス別 SG を app_task の1つに統合した。
# 同一タスク内のコンテナ間通信は localhost で完結し SG を経由しないため、サービス間の許可ルールは無い。

# 集約タスク用 SG。インバウンドは ALB からの admin_ui ポートと、検証タスクからの MCP ポートのみ。
# ADR-0104: タスクはパブリック IP を持つため、インターネットからの到達を止めるのはこの SG だけになる。
# インターネット（0.0.0.0/0 など）からのインバウンドルールは追加しないこと。
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

# --- アウトバウンド（すべての SG は egress 全許可。到達可否は相手側 ingress で制御）---
# AWS サービス（ECR・Logs・Secrets Manager・SSM・Bedrock・S3）への 443 もこの全許可で賄う（ADR-0104）。
locals {
  egress_sgs = {
    app_task          = aws_security_group.app_task.id
    verification_task = aws_security_group.verification_task.id
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
# タスクを置くサブネット（ワークロードサブネット）と、インターネットへの経路の照合（ADR-0104）
# ECS タスク・run-task はパブリックサブネットにパブリック IP 付きで置き、ECR・CloudWatch Logs・
# Secrets Manager・ECS Exec（SSM）・Bedrock・S3 へはインターネットゲートウェイ経由で接続する。
# VPC エンドポイントも NAT ゲートウェイも使わない。外から入ってくる通信は、タスク用 SG の
# インバウンド（ALB・検証タスクからのみ）で止める。RDS はプライベートサブネットのまま。
# ===========================================================================

locals {
  # 未指定なら public_subnet_ids の先頭を使う（ADR-0095 の単一サブネット配置は維持）。
  # private_subnet_ids（2 AZ）は RDS の DB サブネットグループ専用（ADR-0026: 2 AZ 以上が必須）。
  workload_subnet_id = var.workload_subnet_id != null ? var.workload_subnet_id : (
    length(var.public_subnet_ids) > 0 ? var.public_subnet_ids[0] : null
  )

  # ワークロードサブネットが「使う」ルートテーブル。明示的な関連付けが無ければ、
  # サブネットは VPC のメインルートテーブルを暗黙利用している。
  workload_route_table_id = length(data.aws_route_tables.workload_explicit.ids) > 0 ? tolist(data.aws_route_tables.workload_explicit.ids)[0] : data.aws_route_table.main.route_table_id
}

# 注意: association.subnet-id フィルタは "明示的に関連付けられた" RT しか見つけないため、
# メインルートテーブルも別途取得して locals でフォールバックする。
data "aws_route_tables" "workload_explicit" {
  vpc_id = var.vpc_id
  filter {
    name   = "association.subnet-id"
    values = [local.workload_subnet_id]
  }

  lifecycle {
    precondition {
      condition     = local.workload_subnet_id != null
      error_message = "タスクを置くサブネットが決まりません。TF_VAR_workload_subnet_id か TF_VAR_public_subnet_ids にパブリックサブネットを指定してください（ADR-0104）。"
    }
  }
}

data "aws_route_table" "main" {
  vpc_id = var.vpc_id
  filter {
    name   = "association.main"
    values = ["true"]
  }
}

# ワークロードサブネットに 0.0.0.0/0 → インターネットゲートウェイ の経路があることを plan で確かめる。
# 無いと、タスクがイメージを pull できずに起動に失敗する（原因が分かりにくいので先に止める）。
data "aws_route_table" "workload" {
  route_table_id = local.workload_route_table_id

  lifecycle {
    postcondition {
      condition = anytrue([
        for r in self.routes : r.cidr_block == "0.0.0.0/0" && startswith(coalesce(r.gateway_id, "-"), "igw-")
      ])
      error_message = "タスクを置くサブネット ${local.workload_subnet_id} のルートテーブル ${self.id} に 0.0.0.0/0 → インターネットゲートウェイ の経路がありません。パブリックサブネットを TF_VAR_workload_subnet_id に指定してください（ADR-0104）。"
    }
  }
}
