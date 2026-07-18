output "ecs_platform_log_group_name" {
  value = aws_cloudwatch_log_group.ecs_platform.name
}

output "ecs_platform_log_group_arn" {
  value = aws_cloudwatch_log_group.ecs_platform.arn
}

output "operations_dashboard_name" {
  value = aws_cloudwatch_dashboard.operations.dashboard_name
}

output "operations_dashboard_url" {
  value = "https://${data.aws_region.current.name}.console.aws.amazon.com/cloudwatch/home?region=${data.aws_region.current.name}#dashboards:name=${aws_cloudwatch_dashboard.operations.dashboard_name}"
}
