output "ecs_execution_role_arn" {
  value = aws_iam_role.ecs_execution.arn
}

output "ecs_task_role_arn" {
  value = aws_iam_role.ecs_task.arn
}

output "lambda_execution_role_arn" {
  value = aws_iam_role.lambda_execution.arn
}

output "api_key_secret_arn" {
  value = aws_secretsmanager_secret_version.api_key.arn
}

output "api_key_secret_name" {
  value = aws_secretsmanager_secret.api_key.name
}
