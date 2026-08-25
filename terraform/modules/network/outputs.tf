output "vpc_id" {
  value = data.aws_vpc.this.id
}

output "private_subnet_ids" {
  value = var.private_subnet_ids
}

output "sg_agent_invitro_id" {
  value = aws_security_group.agent_invitro.id
}

output "sg_tag_selector_mcp_id" {
  value = aws_security_group.tag_selector_mcp.id
}

output "sg_knowledge_mcp_id" {
  value = aws_security_group.knowledge_mcp.id
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

output "sg_admin_ui_task_id" {
  value = aws_security_group.admin_ui_task.id
}

output "public_subnet_ids" {
  value = var.public_subnet_ids
}
