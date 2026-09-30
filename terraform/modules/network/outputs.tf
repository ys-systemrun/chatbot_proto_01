output "vpc_id" {
  value = data.aws_vpc.this.id
}

output "private_subnet_ids" {
  value = var.private_subnet_ids
}

# ADR-0095: ECS タスク・run-task を置く単一サブネット（run-task API に渡しやすいようリストで返す）。
output "workload_subnet_ids" {
  value = [local.workload_subnet_id]
}

# ADR-0095: 集約タスク（4コンテナ）用 SG。
output "sg_app_task_id" {
  value = aws_security_group.app_task.id
}

output "sg_rds_id" {
  value = aws_security_group.rds.id
}

output "sg_verification_task_id" {
  value = aws_security_group.verification_task.id
}

# IMPL-202608211050 T8/T9: admin_ui（ADR-0041）。app 構成が local.db 経由で参照する。
output "sg_admin_ui_alb_id" {
  value = aws_security_group.admin_ui_alb.id
}

output "public_subnet_ids" {
  value = var.public_subnet_ids
}
