output "ecr_repository_urls" {
  description = "各コンポーネントの ECR リポジトリ URI（イメージ push 先, §5.2）"
  value       = module.ecr.repository_urls
}

output "vpc_id" {
  value = module.network.vpc_id
}

output "private_subnet_ids" {
  description = "run-task の networkConfiguration に使う（§8.1/8.2）"
  value       = module.network.private_subnet_ids
}

output "sg_verification_task_id" {
  description = "run-task（db_hiroba_qa_init / mcp-inspector）の securityGroups に使う"
  value       = module.network.sg_verification_task_id
}

output "cluster_name" {
  value = module.ecs_cluster.cluster_name
}

output "rds_endpoint" {
  value = module.database.endpoint
}

output "db_url_secret_arn" {
  value = module.database.db_url_secret_arn
}

output "db_init_task_family" {
  description = "aws ecs run-task --task-definition に指定（Phase 4, §8.1）"
  value       = module.db_init_task.family
}

output "mcp_inspector_task_family" {
  description = "aws ecs run-task --task-definition に指定（Phase 6, §8.2）"
  value       = module.mcp_inspector_task.family
}

output "bedrock_budget_name" {
  description = "Bedrock 予算アラート名（budget_alert_emails 指定時のみ）"
  value       = length(module.cost_alert) > 0 ? module.cost_alert[0].budget_name : null
}
