# envs/verify（IMPL-202608101542 §3）: 各モジュールの呼び出し。
# 実行順序・依存は §7 参照。Terraform の暗黙依存で概ね順序は解決されるが、
# Phase 4（データ投入）→ Phase 5（knowledge_mcp 起動）だけは手順（README §Phase4/5）で担保する。

locals {
  repo_names = ["knowledge-mcp", "tag-selector-mcp", "agent-invitro", "db-hiroba-qa-init", "mcp-inspector"]

  knowledge_image     = "${module.ecr.repository_urls["knowledge-mcp"]}:${var.image_tag}"
  tag_selector_image  = "${module.ecr.repository_urls["tag-selector-mcp"]}:${var.image_tag}"
  agent_image         = "${module.ecr.repository_urls["agent-invitro"]}:${var.image_tag}"
  db_init_image       = "${module.ecr.repository_urls["db-hiroba-qa-init"]}:${var.image_tag}"
  mcp_inspector_image = "${module.ecr.repository_urls["mcp-inspector"]}:${var.mcp_inspector_image_tag}"

  knowledge_port    = 8100
  tag_selector_port = 8200
}

module "ecr" {
  source           = "../../modules/ecr"
  repository_names = local.repo_names
}

module "network" {
  source                = "../../modules/network"
  name_prefix           = var.name_prefix
  vpc_cidr              = var.vpc_cidr
  availability_zones    = var.availability_zones
  knowledge_mcp_port    = local.knowledge_port
  tag_selector_mcp_port = local.tag_selector_port
  enable_nat_gateway    = var.enable_nat_gateway
}

module "database" {
  source              = "../../modules/database"
  name_prefix         = var.name_prefix
  subnet_ids          = module.network.private_subnet_ids
  security_group_id   = module.network.sg_rds_id
  engine_version      = var.rds_engine_version
  instance_class      = var.rds_instance_class
  multi_az            = false
  deletion_protection = false
}

module "service_discovery" {
  source         = "../../modules/service-discovery"
  namespace_name = var.service_namespace
}

module "ecs_cluster" {
  source       = "../../modules/ecs-cluster"
  cluster_name = "${var.name_prefix}-cluster"
}

# --- tag_selector_mcp（データ非依存, T8 を待たず起動可）---
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
    DATABASE_URL = module.database.db_url_secret_arn
  }

  security_group_ids            = [module.network.sg_tag_selector_mcp_id]
  subnet_ids                    = module.network.private_subnet_ids
  enable_execute_command        = true
  enable_bedrock                = true
  service_connect_namespace_arn = module.service_discovery.namespace_arn
  health_check_command          = ["CMD", "curl", "-f", "http://localhost:${local.tag_selector_port}/health"]
}

# --- knowledge_mcp（Phase 4 完了後に起動: README 手順で担保）---
module "knowledge_mcp" {
  source       = "../../modules/ecs-service"
  service_name = "knowledge_mcp"
  cluster_arn  = module.ecs_cluster.cluster_arn
  region       = var.aws_region
  image_uri    = local.knowledge_image

  container_port = local.knowledge_port
  desired_count  = var.knowledge_mcp_desired_count # Phase4→5 ゲート（deploy.ps1）
  environment = {
    EMBEDDING_PROVIDER          = "bedrock"
    BEDROCK_EMBEDDING_MODEL_ID  = var.bedrock_embedding_model_id
    BEDROCK_REGION              = var.aws_region
    KNOWLEDGE_MCP_DEFAULT_TOP_K = "5"
  }
  secrets = {
    DATABASE_URL = module.database.db_url_secret_arn
  }

  security_group_ids            = [module.network.sg_knowledge_mcp_id]
  subnet_ids                    = module.network.private_subnet_ids
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

  security_group_ids            = [module.network.sg_agent_invitro_id]
  subnet_ids                    = module.network.private_subnet_ids
  enable_execute_command        = true # ADR-0025: 動作確認は ECS Exec（ipython）
  enable_bedrock                = true
  service_connect_namespace_arn = module.service_discovery.namespace_arn
}

# --- db_hiroba_qa_init（タスク定義のみ, run-task で実行, ADR-0030）---
module "db_init_task" {
  source    = "../../modules/db-init-task"
  region    = var.aws_region
  image_uri = local.db_init_image

  environment = {
    EMBEDDING_VECTOR_DIM       = tostring(var.embedding_vector_dim)
    EMBEDDING_PROVIDER         = "bedrock"
    BEDROCK_EMBEDDING_MODEL_ID = var.bedrock_embedding_model_id
    BEDROCK_REGION             = var.aws_region
    CSV_DATA_DIR               = var.csv_data_dir
    QA_ORIGINAL_FILE           = var.qa_original_file
    QUESTION_ALTERED_FILE      = var.question_altered_file
    CATEGORY_FILE              = var.category_file
  }
  secrets = {
    DATABASE_URL = module.database.db_url_secret_arn
  }
  enable_bedrock = true
}

# --- mcp-inspector-task（検証用, 常駐なし, ADR-0029）---
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
