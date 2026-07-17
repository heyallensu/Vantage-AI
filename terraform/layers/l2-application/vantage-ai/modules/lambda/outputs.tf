output "function_name" {
  value = aws_lambda_function.processor.function_name
}

output "function_arn" {
  value = aws_lambda_function.processor.arn
}

output "lambda_security_group_id" {
  value = var.lambda_security_group_id
}

output "event_source_mapping_uuid" {
  value = aws_lambda_event_source_mapping.sqs.uuid
}

output "log_group_name" {
  value = aws_cloudwatch_log_group.lambda.name
}
