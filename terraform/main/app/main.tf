# app 構成（ADR-0039 §4.3 / §5.2）: アプリ側 ECS 常駐サービス周辺リソース。
#
# database 構成の出力（VPC/サブネット・集約タスク用 SG・db_url_secret_arn 等）を
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

  # app 構成が push 先とする ECR リポジトリ（db-init は database 構成へ移設済み, §5.3）。
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

module "ecs_cluster" {
  source       = "../../modules/ecs-cluster"
  cluster_name = "${var.name_prefix}-cluster"
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

# --- 常駐4サービスを1タスク・4コンテナで起動（ADR-0095）---
# 同一タスク内はネットワーク名前空間を共有するため、サービス間の接続先は localhost:<port>。
# Service Connect は使わない。起動順序は dependsOn（MCP サーバの HEALTHY 待ち）で担保する。
# シード完了ゲート（Phase 4→5）はタスク全体の desired_count（app_desired_count）で行う（決定3）。
module "app" {
  source      = "../../modules/ecs-app-task"
  name        = "${var.name_prefix}-app"
  cluster_arn = module.ecs_cluster.cluster_arn
  region      = var.aws_region
  cpu         = var.app_task_cpu
  memory      = var.app_task_memory

  desired_count          = var.app_desired_count
  security_group_ids     = [local.db.sg_app_task_id]
  subnet_ids             = local.db.workload_subnet_ids
  enable_execute_command = true # ADR-0025: ipython による切り分けは --container 指定で引き続き可能
  enable_bedrock         = true # tag_selector_mcp / knowledge_mcp / agent_invitro が使う

  target_group_arn      = module.admin_ui_alb.target_group_arn
  target_container_name = "admin_ui"

  containers = {
    # --- tag_selector_mcp（データ非依存）---
    tag_selector_mcp = {
      image = local.tag_selector_image
      port  = local.tag_selector_port
      environment = {
        LLM_PROVIDER                              = "bedrock"
        BEDROCK_CHAT_MODEL_ID                     = var.bedrock_chat_model_id
        BEDROCK_REGION                            = var.aws_region
        TAXONOMY_RELOAD_INTERVAL_SEC              = "300"
        TAG_SELECTOR_DEFAULT_MAX_TAGS             = "3"
        TAG_SELECTOR_DEFAULT_CONFIDENCE_THRESHOLD = "0.0"
      }
      # ロール分離（ADR-0052 / IMPL-202608261022 T19）: マスター権限の db_url ではなく DML 専用の
      # knowledge_app ロール接続文字列を使う。tag_selector_mcp はタグ台帳の読み取りのみ。
      secrets = {
        DATABASE_URL = local.db.knowledge_app_db_url_secret_arn
      }
      health_check_command = ["CMD", "curl", "-f", "http://localhost:${local.tag_selector_port}/health"]
    }

    # --- knowledge_mcp（seed 完了後に起動: apply-app/apply-all のゲートで担保）---
    knowledge_mcp = {
      image = local.knowledge_image
      port  = local.knowledge_port
      environment = {
        EMBEDDING_PROVIDER          = "bedrock"
        BEDROCK_EMBEDDING_MODEL_ID  = var.bedrock_embedding_model_id
        BEDROCK_REGION              = var.aws_region
        KNOWLEDGE_MCP_DEFAULT_TOP_K = "5"
        # IMPL-202608261450: タグ階層展開・タグ構成類似度スコアリング（ADR-0058・ADR-0059）
        TAG_SIMILARITY_WEIGHT = "0.5"
        # SEARCH_CANDIDATE_POOL_SIZE は未設定のままとし、アプリケーション側の既定計算式に委ねる
        # （5.1節、max(top_k * 10, 50)）。値を固定したくなった場合のみ追加する。
      }
      # ロール分離（ADR-0052 / IMPL-202608261022 T19）: DML 専用の knowledge_app ロール接続文字列。
      secrets = {
        DATABASE_URL = local.db.knowledge_app_db_url_secret_arn
      }
      health_check_command = ["CMD", "curl", "-f", "http://localhost:${local.knowledge_port}/health"]
    }

    # --- agent_invitro（常駐 HTTP サービス, ADR-0043 / IMPL-202608241104 T27）---
    # admin_ui の /api/ask-pipeline・/api/ask-agentic の中継先。DB 資格情報は注入しない。
    agent_invitro = {
      image = local.agent_image
      port  = local.agent_invitro_port
      command = [
        "python", "-m", "uvicorn", "agent_invitro.main.api.server:app",
        "--host", "0.0.0.0", "--port", tostring(local.agent_invitro_port),
      ]
      environment = {
        KNOWLEDGE_MCP_URL     = "http://localhost:${local.knowledge_port}/mcp"
        TAG_SELECTOR_MCP_URL  = "http://localhost:${local.tag_selector_port}/mcp"
        LLM_PROVIDER          = "bedrock"
        BEDROCK_CHAT_MODEL_ID = var.bedrock_chat_model_id
        BEDROCK_REGION        = var.aws_region
        # --- 会話タグ管理機能で追加（IMPL-202608261345 T10 / ADR-0057）---
        # TAG_SEARCH_FALLBACK_ENABLED は ADR-0062 により廃止（単一呼び出し方式へ単純化）。
        TAG_SELECTOR_MAX_TAGS             = "3"
        TAG_SELECTOR_CONFIDENCE_THRESHOLD = "0.0"
        TAG_CONTEXT_MAX_TAGS              = "5"
        TAG_CONTEXT_MAX_MISSED_TURNS      = "2"
      }
      health_check_command = ["CMD", "curl", "-f", "http://localhost:${local.agent_invitro_port}/health"]
      depends_on_healthy   = ["knowledge_mcp", "tag_selector_mcp"]
    }

    # --- admin_ui: 管理UI（web_backend + front_dev ビルド同梱, ADR-0042）---
    # ALB 配下（ADR-0041）。データAPIは全て /api/ 名前空間（SPAページURLとの衝突回避）。
    admin_ui = {
      image = local.admin_ui_image
      port  = local.admin_ui_port
      environment = {
        KNOWLEDGE_MCP_URL = "http://localhost:${local.knowledge_port}/mcp"
        # chat 系（/api/ask-pipeline・/api/ask-agentic）は agent_invitro へ中継する。接続先アドレスの
        # 指定のみで、どちらの方式を使うかはブラウザのトグルが決める（ADR-0045 / ADR-0089 決定5）。
        AGENT_INVITRO_BASE_URL = "http://localhost:${local.agent_invitro_port}"
        # 検証機能（質問→タグ→情報源の検索精度検証, ADR-0049 / IMPL-202608260909 T17）。
        # select_tags を tag_selector_mcp へ直接呼び出す。VERIFICATION_* は検証実行時に
        # select_tags / search_knowledge へ都度渡すパラメータ（機密ではないため平文 environment）。
        TAG_SELECTOR_MCP_URL              = "http://localhost:${local.tag_selector_port}/mcp"
        VERIFICATION_MAX_TAGS             = "3"
        VERIFICATION_CONFIDENCE_THRESHOLD = "0.0"
        VERIFICATION_TOP_K                = "5"
        VERIFICATION_MIN_SCORE            = "0.0"
      }
      # 資格情報スコープの徹底（ADR-0045 / ADR-0095 決定5）: conversation 用とエクスポート読み取り用のみ。
      # マスター権限・knowledge_app の DATABASE_URL は注入しない。
      secrets = {
        # ロール分離（ADR-0052）: DML 専用の conversation_app ロール接続文字列。
        CONVERSATION_DB_URL = local.db.conversation_app_db_url_secret_arn
        # 全データエクスポート（/api/export）用の読み取り専用ロール knowledge_export_reader（ADR-0046）。
        KNOWLEDGE_EXPORT_DB_URL = local.db.knowledge_export_db_url_secret_arn
      }
      # ALB ヘルスチェック（/health）でタスク健全性を判定するため、コンテナ healthCheck は付けない
      # （python:3.11 ベースイメージに curl を前提しない, 10章）。
      depends_on_healthy = ["knowledge_mcp", "tag_selector_mcp"]
    }
  }

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
