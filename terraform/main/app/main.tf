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
  repo_names = ["knowledge-mcp", "tag-selector-mcp", "agent-invitro", "mcp-inspector"]

  knowledge_image     = "${module.ecr.repository_urls["knowledge-mcp"]}:${var.image_tag}"
  tag_selector_image  = "${module.ecr.repository_urls["tag-selector-mcp"]}:${var.image_tag}"
  agent_image         = "${module.ecr.repository_urls["agent-invitro"]}:${var.image_tag}"
  mcp_inspector_image = "${module.ecr.repository_urls["mcp-inspector"]}:${var.mcp_inspector_image_tag}"

  knowledge_port    = 8100
  tag_selector_port = 8200
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

# --- agent_invitro（常駐, ポート無し, ECS Exec 専用, ADR-0025）---
module "agent_invitro" {
  source       = "../../modules/ecs-service"
  service_name = "agent_invitro"
  cluster_arn  = module.ecs_cluster.cluster_arn
  region       = var.aws_region
  image_uri    = local.agent_image

  container_port = null
  command        = ["sleep", "infinity"] # メインプロセスを終了させない（ADR-0025）
  environment = {
    KNOWLEDGE_MCP_URL     = "http://knowledge_mcp:${local.knowledge_port}/mcp"
    TAG_SELECTOR_MCP_URL  = "http://tag_selector_mcp:${local.tag_selector_port}/mcp"
    LLM_PROVIDER          = "bedrock"
    BEDROCK_CHAT_MODEL_ID = var.bedrock_chat_model_id
    BEDROCK_REGION        = var.aws_region
  }

  security_group_ids            = [local.db.sg_agent_invitro_id]
  subnet_ids                    = local.db.private_subnet_ids
  enable_execute_command        = true # ADR-0025: 動作確認は ECS Exec（ipython）
  enable_bedrock                = true
  service_connect_namespace_arn = module.service_discovery.namespace_arn
}

# --- mcp-inspector-task（検証用, 常駐なし, ADR-0029）---
# SG は local.db.sg_verification_task_id を run-task 側（検証手順）で使用。モジュール自体は SG を取らない。
module "mcp_inspector_task" {
  source    = "../../modules/mcp-inspector-task"
  region    = var.aws_region
  image_uri = local.mcp_inspector_image
}

# --- Bedrock コスト予算アラート（メール指定時のみ作成）---
module "cost_alert" {
  count             = length(var.budget_alert_emails) > 0 ? 1 : 0
  source            = "../../modules/cost-alert"
  name              = "${var.name_prefix}-bedrock-monthly"
  monthly_limit_usd = var.bedrock_monthly_budget_usd
  alert_emails      = var.budget_alert_emails
}
