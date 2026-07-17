output "app_security_group_id" { value = aws_security_group.app.id }
output "lambda_security_group_id" { value = aws_security_group.lambda.id }
output "database_security_group_id" { value = aws_security_group.database.id }
output "secretsmanager_endpoint_security_group_id" {
  value = aws_security_group.secrets_endpoint.id
}
