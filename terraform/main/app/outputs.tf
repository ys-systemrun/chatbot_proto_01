# app 構成の出力（ADR-0039 §5.2）。
# private_subnet_ids / sg_verification_task_id / db_init_task_family は database 構成側の出力
# （local.db.*）であり、seed スクリプトは database 構成から直接取得するため、ここでは中継しない。

output "ecr_repository_urls" {
  description = "app 側 4 リポジトリの ECR URI（イメージ push 先, §5.2）"
  value       = module.ecr.repository_urls
}

output "cluster_name" {
  value = module.ecs_cluster.cluster_name
}

output "mcp_inspector_task_family" {
  description = "aws ecs run-task --task-definition に指定（Phase 6 検証, §8.2）"
  value       = module.mcp_inspector_task.family
}

output "bedrock_budget_name" {
  description = "Bedrock 予算アラート名（budget_alert_emails 指定時のみ）"
  value       = length(module.cost_alert) > 0 ? module.cost_alert[0].budget_name : null
}
