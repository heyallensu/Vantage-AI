output "ecs_platform_log_group_name" {
  value = aws_cloudwatch_log_group.ecs_platform.name
}

output "ecs_platform_log_group_arn" {
  value = aws_cloudwatch_log_group.ecs_platform.arn
}