output "db_identifier" {
  value = aws_db_instance.this.identifier
}

output "db_endpoint" {
  value = aws_db_instance.this.endpoint
}

output "db_address" {
  value = aws_db_instance.this.address
}

output "db_port" {
  value = aws_db_instance.this.port
}

output "db_name" {
  value = aws_db_instance.this.db_name
}

output "database_security_group_id" {
  value = var.database_security_group_id
}

output "database_secret_arn" {
  value     = aws_db_instance.this.master_user_secret[0].secret_arn
  sensitive = true
}
