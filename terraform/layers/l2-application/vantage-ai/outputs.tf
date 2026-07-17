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

output "sqs_dlq_name" {
  value = module.sqs.dlq_name
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

output "database_secret_arn" {
  value     = module.rds.database_secret_arn
  sensitive = true
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

output "ecs_cluster_name" {
  value = data.terraform_remote_state.l1.outputs.ecs_cluster_name
}

output "ecs_task_definition_arn" {
  value = module.ecs_service.task_definition_arn
}

output "deployed_image_tag" {
  value = var.app_image_tag
}

output "deployed_image_digest" {
  value = var.app_image_digest
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

output "document_bucket_name" {
  value = module.storage.document_bucket_name
}

output "frontend_bucket_name" {
  value = module.storage.frontend_bucket_name
}

output "cloudfront_distribution_id" {
  value = module.cdn.distribution_id
}

output "cloudfront_url" {
  value = module.cdn.https_url
}

output "api_key_secret_name" {
  value = module.iam.api_key_secret_name
}

output "operations_dashboard_name" {
  value = data.terraform_remote_state.l1.outputs.operations_dashboard_name
}

output "operations_dashboard_url" {
  value = data.terraform_remote_state.l1.outputs.operations_dashboard_url
}

output "s3_vpc_endpoint_id" {
  value = module.vpc_endpoints.s3_endpoint_id
}

output "secretsmanager_vpc_endpoint_id" {
  value = module.vpc_endpoints.secretsmanager_endpoint_id
}

output "cleanup_identifiers" {
  description = "Short-lived resources operators should confirm disappear after L2 destroy."
  value = {
    cloudfront_distribution_id = module.cdn.distribution_id
    document_bucket            = module.storage.document_bucket_name
    frontend_bucket            = module.storage.frontend_bucket_name
    ecs_service                = module.ecs_service.service_name
    lambda_function            = module.lambda_processor.function_name
    queue                      = module.sqs.queue_name
    dead_letter_queue          = module.sqs.dlq_name
    database                   = module.rds.db_identifier
    operations_dashboard       = data.terraform_remote_state.l1.outputs.operations_dashboard_name
  }
}
