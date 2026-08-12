output "vpc_id" {
  value = aws_vpc.this.id
}

output "private_subnet_ids" {
  value = aws_subnet.private[*].id
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
