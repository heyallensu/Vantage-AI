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

  db_name                     = var.db_name
  username                    = var.db_username
  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [var.database_security_group_id]
  publicly_accessible    = false
  multi_az               = false

  backup_retention_period = var.backup_retention_period
  # ADR 001 keeps both controls disabled for the disposable portfolio data, but
  # callers can opt into deletion protection and final snapshots independently.
  deletion_protection = var.deletion_protection
  skip_final_snapshot = var.skip_final_snapshot

  apply_immediately          = true
  auto_minor_version_upgrade = true

  tags = {
    Name  = "${var.name_prefix}-postgres"
    Layer = "l2-application"
  }
}
