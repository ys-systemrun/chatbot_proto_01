# admin-ui-alb モジュール（IMPL-202608211050 T11, ADR-0041, 5.2節）
#
# internet-facing ALB + ターゲットグループ（target_type=ip, Fargate awsvpc 対応）+ HTTP(80) リスナー。
# 0章の暫定方針により HTTPS(443) リスナーは本フェーズでは作成しない（将来 ACM 証明書発行後に追加）。
#
# ALB SG（sg-admin-ui-alb）本体は network モジュール（database 構成）で作成済み。ここでは
# 社内IP（CIDR）からの 80 番インバウンド許可ルールのみを、その SG に追加する（許可 CIDR は
# app 構成の変数 admin_ui_allowed_cidrs, T15/5.4）。

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

resource "aws_lb" "this" {
  name               = "${var.name_prefix}-admin-ui-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [var.alb_security_group_id]
  subnets            = var.public_subnet_ids
  tags               = { Name = "${var.name_prefix}-admin-ui-alb" }
}

resource "aws_lb_target_group" "this" {
  name        = "${var.name_prefix}-admin-ui-tg"
  port        = var.container_port
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip" # Fargate awsvpc は IP ターゲット（5.2節）

  health_check {
    path                = var.health_check_path
    protocol            = "HTTP"
    matcher             = "200"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }

  tags = { Name = "${var.name_prefix}-admin-ui-tg" }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.this.arn
  }
}

# 社内IP（CIDR）からの 80 番インバウンドのみ許可（ADR-0041, 5.1節）。それ以外は SG の既定で拒否。
resource "aws_vpc_security_group_ingress_rule" "alb_from_office" {
  for_each          = toset(var.allowed_cidr_blocks)
  security_group_id = var.alb_security_group_id
  cidr_ipv4         = each.value
  from_port         = 80
  to_port           = 80
  ip_protocol       = "tcp"
  description       = "office CIDR to admin_ui ALB (HTTP)"
}
