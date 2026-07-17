output "sqs_queue_name" {
  value = module.sqs.queue_name
}

output "sqs_queue_arn" {
  value = module.sqs.queue_arn
}

output "sqs_queue_url" {
  value = module.sqs.queue_url
}

output "sqs_dlq_url" {
  value = module.sqs.dlq_url
}

output "sqs_dlq_arn" {
  value = module.sqs.dlq_arn
}

output "db_identifier" {
  value = module.rds.db_identifier
}

output "db_endpoint" {
  value = module.rds.db_endpoint
}

output "db_address" {
  value = module.rds.db_address
}

output "db_port" {
  value = module.rds.db_port
}

output "db_name" {
  value = module.rds.db_name
}
output "database_security_group_id" {
  value = module.rds.database_security_group_id
}

output "ecs_execution_role_arn" {
  value = module.iam.ecs_execution_role_arn
}

output "ecs_task_role_arn" {
  value = module.iam.ecs_task_role_arn
}

output "lambda_execution_role_arn" {
  value = module.iam.lambda_execution_role_arn
}

output "lambda_function_name" {
  value = module.lambda_processor.function_name
}

output "lambda_function_arn" {
  value = module.lambda_processor.function_arn
}

output "lambda_security_group_id" {
  value = module.lambda_processor.lambda_security_group_id
}

output "lambda_event_source_mapping_uuid" {
  value = module.lambda_processor.event_source_mapping_uuid
}

output "lambda_log_group_name" {
  value = module.lambda_processor.log_group_name
}

output "ecs_service_name" {
  value = module.ecs_service.service_name
}

output "ecs_task_definition_arn" {
  value = module.ecs_service.task_definition_arn
}

output "app_security_group_id" {
  value = module.ecs_service.app_security_group_id
}

output "app_target_group_arn" {
  value = module.ecs_service.target_group_arn
}

output "app_listener_rule_arn" {
  value = module.ecs_service.listener_rule_arn
}

output "dlq_alarm_name" {
  value = module.alarm.dlq_alarm_name
}

output "lambda_errors_alarm_name" {
  value = module.alarm.lambda_errors_alarm_name
}
