resource "aws_security_group" "app" {
  name        = "${var.name_prefix}-api-sg"
  description = "Network boundary for the public-subnet ECS task"
  vpc_id      = var.vpc_id

  tags = { Name = "${var.name_prefix}-api-sg", Layer = "l2-application" }
}

resource "aws_security_group" "lambda" {
  name        = "${var.name_prefix}-lambda-sg"
  description = "Network boundary for the private Lambda processor"
  vpc_id      = var.vpc_id

  tags = { Name = "${var.name_prefix}-lambda-sg", Layer = "l2-application" }
}

resource "aws_security_group" "database" {
  name        = "${var.name_prefix}-db-sg"
  description = "PostgreSQL only from the API and processor"
  vpc_id      = var.vpc_id

  tags = { Name = "${var.name_prefix}-db-sg", Layer = "l2-application" }
}

resource "aws_vpc_security_group_ingress_rule" "app_from_alb" {
  security_group_id            = aws_security_group.app.id
  description                  = "FastAPI traffic from the shared ALB"
  referenced_security_group_id = var.alb_security_group_id
  from_port                    = var.container_port
  to_port                      = var.container_port
  ip_protocol                  = "tcp"
}

# trivy:ignore:AWS-0104 The public-subnet ECS task needs HTTPS egress to regional SQS and Bedrock APIs; inbound remains ALB-only.
resource "aws_vpc_security_group_egress_rule" "app_https" {
  security_group_id = aws_security_group.app.id
  description       = "AWS APIs over HTTPS"
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "app_database" {
  security_group_id            = aws_security_group.app.id
  description                  = "PostgreSQL to the managed database"
  referenced_security_group_id = aws_security_group.database.id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "lambda_s3_https" {
  security_group_id = aws_security_group.lambda.id
  description       = "S3 through the gateway endpoint"
  prefix_list_id    = data.aws_prefix_list.s3.id
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
}

resource "aws_security_group" "secrets_endpoint" {
  name        = "${var.name_prefix}-secrets-endpoint-sg"
  description = "Secrets Manager endpoint access from application runtimes"
  vpc_id      = var.vpc_id

  tags = { Name = "${var.name_prefix}-secrets-endpoint-sg", Layer = "l2-application" }
}

resource "aws_vpc_security_group_ingress_rule" "secrets_from_app" {
  security_group_id            = aws_security_group.secrets_endpoint.id
  referenced_security_group_id = aws_security_group.app.id
  description                  = "Secrets Manager from ECS"
  from_port                    = 443
  to_port                      = 443
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_ingress_rule" "secrets_from_lambda" {
  security_group_id            = aws_security_group.secrets_endpoint.id
  referenced_security_group_id = aws_security_group.lambda.id
  description                  = "Secrets Manager from Lambda"
  from_port                    = 443
  to_port                      = 443
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "lambda_secrets_https" {
  security_group_id            = aws_security_group.lambda.id
  referenced_security_group_id = aws_security_group.secrets_endpoint.id
  description                  = "Secrets Manager through the interface endpoint"
  from_port                    = 443
  to_port                      = 443
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "lambda_database" {
  security_group_id            = aws_security_group.lambda.id
  description                  = "PostgreSQL to the managed database"
  referenced_security_group_id = aws_security_group.database.id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_ingress_rule" "database_from_app" {
  security_group_id            = aws_security_group.database.id
  description                  = "PostgreSQL from the API task"
  referenced_security_group_id = aws_security_group.app.id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_ingress_rule" "database_from_lambda" {
  security_group_id            = aws_security_group.database.id
  description                  = "PostgreSQL from the Lambda processor"
  referenced_security_group_id = aws_security_group.lambda.id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
}
data "aws_prefix_list" "s3" {
  name = "com.amazonaws.${var.aws_region}.s3"
}
