data "aws_ec2_managed_prefix_list" "cloudfront_origin" {
  name = "com.amazonaws.global.cloudfront.origin-facing"
}

resource "aws_security_group" "alb" {
  name        = "${var.name_prefix}-shared-alb-sg"
  description = "Allow HTTP traffic to the shared ALB"
  vpc_id      = var.vpc_id

  tags = {
    Name  = "${var.name_prefix}-shared-alb-sg"
    Layer = "l1-platform"
  }
}


resource "aws_vpc_security_group_ingress_rule" "http_from_cloudfront" {
  security_group_id = aws_security_group.alb.id
  description       = "HTTP only from the AWS-managed CloudFront origin-facing network"
  prefix_list_id    = data.aws_ec2_managed_prefix_list.cloudfront_origin.id
  from_port         = 80
  to_port           = 80
  ip_protocol       = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "application" {
  security_group_id = aws_security_group.alb.id
  description       = "Forward requests to application targets"
  cidr_ipv4         = var.vpc_cidr
  from_port         = var.application_port
  to_port           = var.application_port
  ip_protocol       = "tcp"
}

# trivy:ignore:AWS-0053 Public ALB is required as the CloudFront custom origin; its SG allows only the managed origin prefix list.
resource "aws_lb" "this" {
  name                       = "${var.name_prefix}-shared-alb"
  load_balancer_type         = "application"
  internal                   = false
  security_groups            = [aws_security_group.alb.id]
  subnets                    = var.public_subnet_ids
  drop_invalid_header_fields = true

  tags = {
    Name  = "${var.name_prefix}-shared-alb"
    Layer = "l1-platform"
  }

}

# trivy:ignore:AWS-0054 The default CloudFront domain provides viewer TLS; ADR 003 accepts HTTP on the allowlisted demo origin.
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
