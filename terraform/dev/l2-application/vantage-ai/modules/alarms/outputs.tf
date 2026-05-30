output "dlq_alarm_name" {
  value = aws_cloudwatch_metric_alarm.dlq_visible_messages.alarm_name
}

output "lambda_errors_alarm_name" {
  value = aws_cloudwatch_metric_alarm.lambda_errors.alarm_name
}