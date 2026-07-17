resource "aws_security_group" "alb" {
  name        = "${var.name_prefix}-shared-alb-sg"
  description = "Allow HTTP traffic to the shared ALB"
  vpc_id      = var.vpc_id

  tags = {
    Name  = "${var.name_prefix}-shared-alb-sg"
    Layer = "l1-platform"
  }
}


resource "aws_vpc_security_group_ingress_rule" "http" {
  security_group_id = aws_security_group.alb.id
  description       = "HTTP from internet"
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 80
  to_port           = 80
  ip_protocol       = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "all" {
  security_group_id = aws_security_group.alb.id
  description       = "All traffic to internet"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}

resource "aws_lb" "this" {
  name               = "${var.name_prefix}-shared-alb"
  load_balancer_type = "application"
  internal           = false
  security_groups    = [aws_security_group.alb.id]
  subnets            = var.public_subnet_ids

  tags = {
    Name  = "${var.name_prefix}-shared-alb"
    Layer = "l1-platform"
  }

}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"
  default_action {
    type = "fixed-response"
    fixed_response {
      content_type = "text/plain"
      message_body = "No application route configured"
      status_code  = "404"
    }
  }
}