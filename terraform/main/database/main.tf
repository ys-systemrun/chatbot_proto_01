# database 構成（ADR-0039 §4.2 / §5.1）: ネットワーク基盤 + RDS + シード用 ECS 周辺リソース。
#
# 旧 3 層（verify-network / verify-database / verify の db_init 部分）を1つの root に統合したもの。
# 重要（§10）: network ↔ database ↔ db_init_task は同一 root 内に統合されたため、
# 層間の値受け渡しは terraform_remote_state ではなく通常のモジュール出力参照
# （module.network.xxx / module.database.xxx）で完結する。database 構成内では
# terraform_remote_state を一切使用しない（app 構成からの片方向参照のみで使う, ADR-0039）。

locals {
  knowledge_mcp_port    = 8100
  tag_selector_mcp_port = 8200
  agent_invitro_port    = 8300 # ADR-0043 / IMPL-202608241104 T25
}

# --- ネットワーク基盤（既存VPC参照 + SG + VPCエンドポイント, ADR-0036）---
module "network" {
  source                = "../../modules/network"
  name_prefix           = var.name_prefix
  vpc_id                = var.vpc_id
  private_subnet_ids    = var.private_subnet_ids
  public_subnet_ids     = var.public_subnet_ids
  admin_ui_port         = var.admin_ui_port
  create_vpc_endpoints  = var.create_vpc_endpoints
  knowledge_mcp_port    = local.knowledge_mcp_port
  tag_selector_mcp_port = local.tag_selector_mcp_port
  agent_invitro_port    = local.agent_invitro_port
}

# --- RDS(pgvector) + DBサブネットグループ + DATABASE_URL シークレット（ADR-0037, 永続化）---
module "database" {
  source            = "../../modules/database"
  name_prefix       = var.name_prefix
  subnet_ids        = module.network.private_subnet_ids
  security_group_id = module.network.sg_rds_id
  engine_version    = var.rds_engine_version
  instance_class    = var.rds_instance_class
  multi_az          = var.multi_az

  # 会話評価用データベース名（ADR-0044 / T21）。接続 URL シークレットのデータベース名に使う。
  conversation_db_name = var.conversation_db_name

  # ADR-0037: 永続化運用（通常 destroy の対象外）。
  deletion_protection = var.deletion_protection
  skip_final_snapshot = var.skip_final_snapshot
}

# --- シード用イメージの ECR リポジトリ（db-hiroba-qa-init のみ, ADR-0039 §5.3）---
module "ecr" {
  source           = "../../modules/ecr"
  repository_names = ["db-hiroba-qa-init"]
}

# --- db_hiroba_qa_init（タスク定義のみ, run-task で実行, ADR-0030。旧 verify から移設）---
module "db_init_task" {
  source    = "../../modules/db-init-task"
  region    = var.aws_region
  image_uri = "${module.ecr.repository_urls["db-hiroba-qa-init"]}:${var.image_tag}"

  environment = {
    EMBEDDING_VECTOR_DIM       = tostring(var.embedding_vector_dim)
    EMBEDDING_PROVIDER         = "bedrock"
    BEDROCK_EMBEDDING_MODEL_ID = var.bedrock_embedding_model_id
    BEDROCK_REGION             = var.aws_region
    CSV_DATA_DIR               = var.csv_data_dir
    QA_ORIGINAL_FILE           = var.qa_original_file
    QUESTION_ALTERED_FILE      = var.question_altered_file
    CATEGORY_FILE              = var.category_file
    # conversation データベースの作成・スキーマ適用（ADR-0044 / IMPL-202608241104 T29）。
    CONVERSATION_DB_NAME = var.conversation_db_name
    # エクスポート専用ロールの GRANT CONNECT ON DATABASE の対象名（ADR-0046 / IMPL-202608241600 T10）。
    # db_hiroba_qa_init 側デフォルト "chatbot" と一致する module.database.db_name を渡す。
    CHATBOT_DB_NAME = module.database.db_name
  }
  secrets = {
    DATABASE_URL = module.database.db_url_secret_arn
    # ensure_conversation_database()（DATABASE_URL 使用）と apply_conversation_schema()
    # （CONVERSATION_DB_URL 使用）で参照する（T16/T17/T29）。
    CONVERSATION_DB_URL = module.database.conversation_db_url_secret_arn
    # ensure_export_reader_role() が CREATE ROLE / ALTER ROLE ... PASSWORD に使う生パスワード
    # （ADR-0046 / IMPL-202608241600 T9）。
    EXPORT_READER_PASSWORD = module.database.export_reader_password_secret_arn
  }
  enable_bedrock = true
}
