resource "aws_security_group" "database" {
  name        = "${var.name_prefix}-db-sg"
  description = "Allow PostgreSQL access from Vantage AI application components"
  vpc_id      = var.vpc_id

  tags = {
    Name  = "${var.name_prefix}-db-sg"
    Layer = "l2-application"
  }
}

resource "aws_vpc_security_group_ingress_rule" "postgre_from_vpc" {
  security_group_id = aws_security_group.database.id
  description       = "PostgreSQL from VPC private components"
  cidr_ipv4         = var.vpc_cidr
  from_port         = 5432
  to_port           = 5432
  ip_protocol       = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "database_all" {
  security_group_id = aws_security_group.database.id
  description       = "Outbound traffic from database security group"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}

resource "aws_db_subnet_group" "this" {
  name       = "${var.name_prefix}-postgres-subnets"
  subnet_ids = var.private_subnet_ids

  tags = {
    Name  = "${var.name_prefix}-postgres-subnets"
    Layer = "l2-application"
  }
}

resource "aws_db_instance" "this" {
  identifier = "${var.name_prefix}-postgres"

  engine         = "postgres"
  instance_class = var.db_instance_class

  allocated_storage = var.db_allocated_storage
  storage_type      = "gp3"
  storage_encrypted = true

  db_name  = var.db_name
  username = var.db_username
  password = var.db_password

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.database.id]
  publicly_accessible    = false

  backup_retention_period = var.backup_retention_period
  skip_final_snapshot     = var.skip_final_snapshot

  apply_immediately          = true
  auto_minor_version_upgrade = true

  tags = {
    Name  = "${var.name_prefix}-postgres"
    Layer = "l2-application"
  }
}
