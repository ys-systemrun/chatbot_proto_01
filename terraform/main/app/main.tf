# app 構成（ADR-0039 §4.3 / §5.2）: アプリ側 ECS 常駐サービス周辺リソース。
#
# database 構成の出力（VPC/サブネット・各サービス用 SG・db_url_secret_arn 等）を
# terraform_remote_state で参照する片方向依存（ADR-0039）。database 構成を先に apply しておくこと。
# 旧 verify にあった network / database 2つの remote_state は、database 構成の出力に旧 network の
# 出力も統合されたため、この1つ（database）に集約される（§5.3）。

data "terraform_remote_state" "database" {
  backend = "s3"
  config = {
    bucket = var.state_bucket
    key    = var.state_key_database
    region = var.aws_region
  }
}

locals {
  db = data.terraform_remote_state.database.outputs

  # app 構成が push 先とする ECR リポジトリ（db-hiroba-qa-init は database 構成へ移設済み, §5.3）。
  # admin-ui（管理UI, IMPL-202608211050 T14）を追加。
  repo_names = ["knowledge-mcp", "tag-selector-mcp", "agent-invitro", "mcp-inspector", "admin-ui"]

  knowledge_image     = "${module.ecr.repository_urls["knowledge-mcp"]}:${var.image_tag}"
  tag_selector_image  = "${module.ecr.repository_urls["tag-selector-mcp"]}:${var.image_tag}"
  agent_image         = "${module.ecr.repository_urls["agent-invitro"]}:${var.image_tag}"
  mcp_inspector_image = "${module.ecr.repository_urls["mcp-inspector"]}:${var.mcp_inspector_image_tag}"
  admin_ui_image      = "${module.ecr.repository_urls["admin-ui"]}:${var.image_tag}"

  knowledge_port     = 8100
  tag_selector_port  = 8200
  admin_ui_port      = 8000
  agent_invitro_port = 8300 # ADR-0043 / IMPL-202608241104 T27
}

module "ecr" {
  source           = "../../modules/ecr"
  repository_names = local.repo_names
}

module "service_discovery" {
  source         = "../../modules/service-discovery"
  namespace_name = var.service_namespace
}

module "ecs_cluster" {
  source       = "../../modules/ecs-cluster"
  cluster_name = "${var.name_prefix}-cluster"
}

# --- tag_selector_mcp（データ非依存, seed を待たず起動可）---
module "tag_selector_mcp" {
  source       = "../../modules/ecs-service"
  service_name = "tag_selector_mcp"
  cluster_arn  = module.ecs_cluster.cluster_arn
  region       = var.aws_region
  image_uri    = local.tag_selector_image

  container_port = local.tag_selector_port
  environment = {
    LLM_PROVIDER                              = "bedrock"
    BEDROCK_CHAT_MODEL_ID                     = var.bedrock_chat_model_id
    BEDROCK_REGION                            = var.aws_region
    TAXONOMY_RELOAD_INTERVAL_SEC              = "300"
    TAG_SELECTOR_DEFAULT_MAX_TAGS             = "3"
    TAG_SELECTOR_DEFAULT_CONFIDENCE_THRESHOLD = "0.0"
  }
  secrets = {
    DATABASE_URL = local.db.db_url_secret_arn
  }

  security_group_ids            = [local.db.sg_tag_selector_mcp_id]
  subnet_ids                    = local.db.private_subnet_ids
  enable_execute_command        = true
  enable_bedrock                = true
  service_connect_namespace_arn = module.service_discovery.namespace_arn
  health_check_command          = ["CMD", "curl", "-f", "http://localhost:${local.tag_selector_port}/health"]
}

# --- knowledge_mcp（seed 完了後に起動: apply-app/apply-all のゲートで担保）---
module "knowledge_mcp" {
  source       = "../../modules/ecs-service"
  service_name = "knowledge_mcp"
  cluster_arn  = module.ecs_cluster.cluster_arn
  region       = var.aws_region
  image_uri    = local.knowledge_image

  container_port = local.knowledge_port
  desired_count  = var.knowledge_mcp_desired_count # seed 完了まで 0（Phase4→5 ゲート）
  environment = {
    EMBEDDING_PROVIDER          = "bedrock"
    BEDROCK_EMBEDDING_MODEL_ID  = var.bedrock_embedding_model_id
    BEDROCK_REGION              = var.aws_region
    KNOWLEDGE_MCP_DEFAULT_TOP_K = "5"
  }
  secrets = {
    DATABASE_URL = local.db.db_url_secret_arn
  }

  security_group_ids            = [local.db.sg_knowledge_mcp_id]
  subnet_ids                    = local.db.private_subnet_ids
  enable_execute_command        = true
  enable_bedrock                = true
  service_connect_namespace_arn = module.service_discovery.namespace_arn
  health_check_command          = ["CMD", "curl", "-f", "http://localhost:${local.knowledge_port}/health"]
}

# --- agent_invitro（常駐 HTTP サービス化, ADR-0043 / IMPL-202608241104 T27）---
# 従来の ECS Exec 専用（sleep infinity, ADR-0025）から、admin_ui の /ask-sl 中継先となる
# 常駐 HTTP サービス（FastAPI + Uvicorn, ポート 8300）へ変更する。ALB 配下ではないため
# /health はコンテナヘルスチェック専用（ALB ターゲットグループのヘルスチェックとは別物, 10章）。
module "agent_invitro" {
  source       = "../../modules/ecs-service"
  service_name = "agent_invitro"
  cluster_arn  = module.ecs_cluster.cluster_arn
  region       = var.aws_region
  image_uri    = local.agent_image

  container_port = local.agent_invitro_port
  command = [
    "python", "-m", "uvicorn", "agent_invitro.main.api.server:app",
    "--host", "0.0.0.0", "--port", tostring(local.agent_invitro_port),
  ]
  environment = {
    KNOWLEDGE_MCP_URL     = "http://knowledge_mcp:${local.knowledge_port}/mcp"
    TAG_SELECTOR_MCP_URL  = "http://tag_selector_mcp:${local.tag_selector_port}/mcp"
    LLM_PROVIDER          = "bedrock"
    BEDROCK_CHAT_MODEL_ID = var.bedrock_chat_model_id
    BEDROCK_REGION        = var.aws_region
  }

  security_group_ids            = [local.db.sg_agent_invitro_id]
  subnet_ids                    = local.db.private_subnet_ids
  enable_execute_command        = true # ADR-0025: ipython による切り分けは引き続き可能
  enable_bedrock                = true
  service_connect_namespace_arn = module.service_discovery.namespace_arn
  health_check_command          = ["CMD", "curl", "-f", "http://localhost:${local.agent_invitro_port}/health"]
}

# --- mcp-inspector-task（検証用, 常駐なし, ADR-0029）---
# SG は local.db.sg_verification_task_id を run-task 側（検証手順）で使用。モジュール自体は SG を取らない。
module "mcp_inspector_task" {
  source    = "../../modules/mcp-inspector-task"
  region    = var.aws_region
  image_uri = local.mcp_inspector_image
}

# --- admin_ui: ALB（internet-facing, 社内IP限定）---（IMPL-202608211050 T11/T14, ADR-0041）
module "admin_ui_alb" {
  source                = "../../modules/admin-ui-alb"
  name_prefix           = var.name_prefix
  vpc_id                = local.db.vpc_id
  public_subnet_ids     = local.db.public_subnet_ids
  alb_security_group_id = local.db.sg_admin_ui_alb_id
  container_port        = local.admin_ui_port
  allowed_cidr_blocks   = var.admin_ui_allowed_cidrs
  health_check_path     = "/health"
}

# --- admin_ui: 管理UI（web_backend + front_dev ビルド同梱, ADR-0042）---
# ALB 配下だがタスク自体はプライベートサブネット・assign_public_ip=false（既存パターン, ADR-0041 T13）。
# QA/タグ管理は /api/* 経由で Knowledge MCP を呼ぶため KNOWLEDGE_MCP_URL のみ設定（6.2節）。
# データAPIは全て /api/ 名前空間へ揃えた（SPAページURLとの衝突回避）。chat 系（/api/ask-sl 等）の
# 環境変数は AWS では未設定（src/main/config.py が空文字許容, 10章）。
module "admin_ui" {
  source       = "../../modules/ecs-service"
  service_name = "admin_ui"
  cluster_arn  = module.ecs_cluster.cluster_arn
  region       = var.aws_region
  image_uri    = local.admin_ui_image

  container_port   = local.admin_ui_port
  target_group_arn = module.admin_ui_alb.target_group_arn
  environment = {
    KNOWLEDGE_MCP_URL = "http://knowledge_mcp:${local.knowledge_port}/mcp"
    # chat 系（/api/ask-sl）は agent_invitro へ中継する（中継先は agent_invitro 側の /ask-sl,
    # ADR-0045 / IMPL-202608241104 T28）。
    AGENT_INVITRO_URL = "http://agent_invitro:${local.agent_invitro_port}"
  }
  # 会話評価（/api/evaluate_response, /api/evaluated_messages）用（ADR-0045 / T28）。
  # 資格情報スコープの徹底（10章）: ここには conversation データベース用の CONVERSATION_DB_URL のみを
  # 注入し、chatbot データベース用の DATABASE_URL は注入しない（ネットワークは到達可能でも
  # 資格情報で chatbot データベースへのアクセスを防ぐ、ADR-0045）。
  secrets = {
    CONVERSATION_DB_URL = local.db.conversation_db_url_secret_arn
    # 全データエクスポート機能（/api/export）が chatbot データベースを読むための、読み取り専用
    # ロール chatbot_export_reader での接続文字列（ADR-0046 / IMPL-202608241600 T12）。マスター権限の
    # DATABASE_URL は依然として注入しない（資格情報スコープの徹底, ADR-0045/ADR-0046）。ネットワークは
    # 既存 rds_from_admin_ui ルール（admin_ui_task → rds:5432, ADR-0045）でそのまま到達可能（T13）。
    CHATBOT_EXPORT_DB_URL = local.db.chatbot_export_db_url_secret_arn
  }

  security_group_ids            = [local.db.sg_admin_ui_task_id]
  subnet_ids                    = local.db.private_subnet_ids
  enable_execute_command        = true
  enable_bedrock                = false # admin_ui は Bedrock を直接呼ばない（Knowledge MCP 経由）
  service_connect_namespace_arn = module.service_discovery.namespace_arn
  # ALB ヘルスチェック（/health）でタスク健全性を判定するため、コンテナ healthCheck は付けない
  # （python:3.11 ベースイメージに curl を前提しない, 10章）。

  depends_on = [module.admin_ui_alb]
}

# --- Bedrock コスト予算アラート（メール指定時のみ作成）---
module "cost_alert" {
  count             = length(var.budget_alert_emails) > 0 ? 1 : 0
  source            = "../../modules/cost-alert"
  name              = "${var.name_prefix}-bedrock-monthly"
  monthly_limit_usd = var.bedrock_monthly_budget_usd
  alert_emails      = var.budget_alert_emails
}
