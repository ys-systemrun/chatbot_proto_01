# database 構成の出力（ADR-0039 §5.1）。app 構成が terraform_remote_state で参照する。
# sg_rds_id は database 構成内で完結するため出力しない（app 構成には不要）。

output "vpc_id" {
  value = module.network.vpc_id
}

output "private_subnet_ids" {
  description = "run-task の networkConfiguration / ECS サービスの subnets に使う"
  value       = module.network.private_subnet_ids
}

output "sg_agent_invitro_id" {
  value = module.network.sg_agent_invitro_id
}

output "sg_tag_selector_mcp_id" {
  value = module.network.sg_tag_selector_mcp_id
}

output "sg_knowledge_mcp_id" {
  value = module.network.sg_knowledge_mcp_id
}

output "sg_verification_task_id" {
  description = "run-task（db_hiroba_qa_init / mcp-inspector）の securityGroups に使う"
  value       = module.network.sg_verification_task_id
}

# IMPL-202608211050 T9 / ADR-0041: admin_ui（app 構成が terraform_remote_state で参照）。
output "sg_admin_ui_alb_id" {
  description = "admin_ui ALB 用 SG（app 構成の admin-ui-alb モジュールが関連付け）"
  value       = module.network.sg_admin_ui_alb_id
}

output "sg_admin_ui_task_id" {
  description = "admin_ui ECS タスク用 SG（app 構成の ecs-service に渡す）"
  value       = module.network.sg_admin_ui_task_id
}

output "public_subnet_ids" {
  description = "admin_ui の ALB（internet-facing）配置用パブリックサブネット"
  value       = module.network.public_subnet_ids
}

output "db_url_secret_arn" {
  description = "DATABASE_URL を1本の文字列として持つシークレット ARN（app 構成が参照）"
  value       = module.database.db_url_secret_arn
}

# ADR-0044 / IMPL-202608241104 T26/T28: admin_ui の CONVERSATION_DB_URL に注入する。
# app 構成が terraform_remote_state 経由で local.db.conversation_db_url_secret_arn として参照する。
output "conversation_db_url_secret_arn" {
  description = "CONVERSATION_DB_URL を1本の文字列として持つシークレット ARN（app 構成が参照, ADR-0044）"
  value       = module.database.conversation_db_url_secret_arn
}

# ADR-0046 / IMPL-202608241600 T11: admin_ui の CHATBOT_EXPORT_DB_URL に注入する。
# app 構成が terraform_remote_state 経由で local.db.chatbot_export_db_url_secret_arn として参照する。
output "chatbot_export_db_url_secret_arn" {
  description = "CHATBOT_EXPORT_DB_URL を1本の文字列として持つシークレット ARN（app 構成が参照, ADR-0046）"
  value       = module.database.chatbot_export_db_url_secret_arn
}

# ADR-0052 / IMPL-202608261022 T19: アプリ用ロール（_app）の接続文字列シークレットを app 構成へ渡す。
# chatbot_app は knowledge_mcp / tag_selector_mcp / admin_ui の DATABASE_URL、conversation_app は
# admin_ui の CONVERSATION_DB_URL に注入する。app 構成が terraform_remote_state 経由で
# local.db.chatbot_app_db_url_secret_arn / local.db.conversation_app_db_url_secret_arn として参照する。
# migrator/app の生パスワードシークレットは db_init_task が同一 root 内で直接参照するため再エクスポートしない
# （export_reader_password_secret_arn と同じ扱い）。
output "chatbot_app_db_url_secret_arn" {
  description = "chatbot_app ロールでの DATABASE_URL を持つシークレット ARN（app 構成が参照, ADR-0052）"
  value       = module.database.chatbot_app_db_url_secret_arn
}

output "conversation_app_db_url_secret_arn" {
  description = "conversation_app ロールでの CONVERSATION_DB_URL を持つシークレット ARN（app 構成が参照, ADR-0052）"
  value       = module.database.conversation_app_db_url_secret_arn
}

output "rds_endpoint" {
  value = module.database.endpoint
}

output "rds_port" {
  value = module.database.port
}

output "db_name" {
  value = module.database.db_name
}

output "db_init_task_family" {
  description = "aws ecs run-task --task-definition に指定（seed, §6.7）"
  value       = module.db_init_task.family
}

# ADR-0066: 全データインポート（全消去→上書き）バッチが、投入ダンプのアップロード先／
# 退避バックアップの保存先として使う S3 バケット名（deploy import-data が参照）。
output "import_bucket_name" {
  description = "全データインポート用 S3 バケット名（import/ ・ rollback/ プレフィックス, ADR-0066）"
  value       = aws_s3_bucket.import_data.id
}

output "ecr_repository_urls" {
  description = "シード用 ECR リポジトリ（db-hiroba-qa-init のみ）のマップ"
  value       = module.ecr.repository_urls
}
