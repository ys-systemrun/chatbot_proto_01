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

output "db_url_secret_arn" {
  description = "DATABASE_URL を1本の文字列として持つシークレット ARN（app 構成が参照）"
  value       = module.database.db_url_secret_arn
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

output "ecr_repository_urls" {
  description = "シード用 ECR リポジトリ（db-hiroba-qa-init のみ）のマップ"
  value       = module.ecr.repository_urls
}
