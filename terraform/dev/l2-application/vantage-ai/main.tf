terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

locals {
  environment = terraform.workspace == "default" ? var.environment : terraform.workspace
  name_prefix = "${var.project_name}-${local.environment}"

  database_url = "postgresql://${var.db_username}:${var.db_password}@${module.rds.db_address}:${module.rds.db_port}/${module.rds.db_name}"

  lambda_package_path = abspath("${path.root}/${var.lambda_package_path}")
}

data "terraform_remote_state" "l0" {
  backend = "local"

  config = {
    path = "../../l0-foundation/terraform.tfstate.d/dev/terraform.tfstate"
  }
}

data "terraform_remote_state" "l1" {
  backend = "local"

  config = {
    path = "../../l1-platform/terraform.tfstate.d/dev/terraform.tfstate"
  }
}

module "sqs" {
  source = "./modules/sqs"

  name_prefix                = local.name_prefix
  visibility_timeout_seconds = var.queue_visibility_timeout_seconds
  message_retention_seconds  = var.queue_message_retention_seconds
  max_receive_count          = var.queue_max_receive_count
}

module "rds" {
  source = "./modules/rds"

  name_prefix             = local.name_prefix
  vpc_id                  = data.terraform_remote_state.l0.outputs.vpc_id
  vpc_cidr                = data.terraform_remote_state.l0.outputs.vpc_cidr
  private_subnet_ids      = data.terraform_remote_state.l0.outputs.private_subnet_ids
  db_name                 = var.db_name
  db_username             = var.db_username
  db_password             = var.db_password
  db_instance_class       = var.db_instance_class
  db_allocated_storage    = var.db_allocated_storage
  backup_retention_period = var.db_backup_retention_period
  skip_final_snapshot     = var.db_skip_final_snapshot
}

module "iam" {
  source = "./modules/iam"

  name_prefix   = local.name_prefix
  sqs_queue_arn = module.sqs.queue_arn
}

module "lambda_processor" {
  source = "./modules/lambda"

  name_prefix               = local.name_prefix
  lambda_package_path       = local.lambda_package_path
  lambda_runtime            = var.lambda_runtime
  lambda_handler            = var.lambda_handler
  lambda_timeout_seconds    = var.lambda_timeout_seconds
  lambda_memory_size        = var.lambda_memory_size
  lambda_execution_role_arn = module.iam.lambda_execution_role_arn
  private_subnet_ids        = data.terraform_remote_state.l0.outputs.private_subnet_ids
  vpc_id                    = data.terraform_remote_state.l0.outputs.vpc_id
  sqs_queue_arn             = module.sqs.queue_arn
  database_url              = local.database_url

  depends_on = [module.iam]
}

module "ecs_service" {
  source = "./modules/ecs-service"

  name_prefix            = local.name_prefix
  vpc_id                 = data.terraform_remote_state.l0.outputs.vpc_id
  subnet_ids             = data.terraform_remote_state.l0.outputs.public_subnet_ids
  assign_public_ip       = true
  alb_security_group_id  = data.terraform_remote_state.l1.outputs.shared_alb_security_group_id
  shared_listener_arn    = data.terraform_remote_state.l1.outputs.shared_http_listener_arn
  ecs_cluster_id         = data.terraform_remote_state.l1.outputs.ecs_cluster_id
  ecr_repository_url     = data.terraform_remote_state.l1.outputs.ecr_repository_url
  log_group_name         = data.terraform_remote_state.l1.outputs.ecs_platform_log_group_name
  ecs_execution_role_arn = module.iam.ecs_execution_role_arn
  ecs_task_role_arn      = module.iam.ecs_task_role_arn
  container_port         = var.app_container_port
  desired_count          = var.app_desired_count
  cpu                    = var.app_cpu
  memory                 = var.app_memory
  image_tag              = var.app_image_tag
  health_check_path      = var.health_check_path
  sqs_queue_url          = module.sqs.queue_url
  database_url           = local.database_url
  bedrock_model_id       = var.bedrock_model_id
}


module "alarm" {
  source = "./modules/alarms"

  name_prefix                    = local.name_prefix
  dlq_name                       = module.sqs.dlq_name
  lambda_function_name           = module.lambda_processor.function_name
  alarm_actions                  = var.alarm_actions
  lambda_error_threshold         = var.lambda_error_threshold
  dlq_visible_messages_threshold = var.dlq_visible_messages_threshold
}
