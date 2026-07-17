output "service_name" {
  value = aws_ecs_service.app.name
}

output "task_definition_arn" {
  value = aws_ecs_task_definition.app.arn
}

output "app_security_group_id" {
  value = var.app_security_group_id
}

output "target_group_arn" {
  value = aws_lb_target_group.app.arn
}

output "listener_rule_arn" {
  value = aws_lb_listener_rule.app.arn
}
