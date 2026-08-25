output "target_group_arn" {
  description = "ecs-service モジュールの load_balancer ブロックに渡す（T12/T14）"
  value       = aws_lb_target_group.this.arn
}

output "dns_name" {
  description = "ブラウザからのアクセス先（http://<dns_name>/, 8.1節）"
  value       = aws_lb.this.dns_name
}

output "alb_arn" {
  value = aws_lb.this.arn
}

# ECS サービスが load_balancer 接続する前にリスナーが存在している必要があるため、
# app 構成側で depends_on に使えるようリスナー ARN を公開する。
output "listener_arn" {
  value = aws_lb_listener.http.arn
}
