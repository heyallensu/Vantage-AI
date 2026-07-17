terraform {
  required_version = ">= 1.10.0"

  backend "s3" {}

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region              = var.aws_region
  allowed_account_ids = [var.allowed_account_id]

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = terraform.workspace
      Owner       = var.owner
      ManagedBy   = "Terraform"
      ExpiresAt   = var.expires_at
    }
  }
}

data "aws_caller_identity" "current" {}

check "caller_account_is_allowed" {
  assert {
    condition     = data.aws_caller_identity.current.account_id == var.allowed_account_id
    error_message = "Refusing to operate outside the explicitly allowed AWS account."
  }
}

locals {
  environment = terraform.workspace
  name_prefix = "${var.project_name}-${local.environment}"

  lambda_package_path = abspath("${path.root}/${var.lambda_package_path}")
}

data "terraform_remote_state" "l0" {
  backend   = "s3"
  workspace = terraform.workspace

  config = {
    bucket               = var.state_bucket
    key                  = "l0-foundation/terraform.tfstate"
    region               = var.state_region
    workspace_key_prefix = var.state_workspace_key_prefix
    allowed_account_ids  = [var.allowed_account_id]
  }
}

data "terraform_remote_state" "l1" {
  backend   = "s3"
  workspace = terraform.workspace

  config = {
    bucket               = var.state_bucket
    key                  = "l1-platform/terraform.tfstate"
    region               = var.state_region
    workspace_key_prefix = var.state_workspace_key_prefix
    allowed_account_ids  = [var.allowed_account_id]
  }
}

module "storage" {
  source = "./modules/storage"

  name_prefix             = local.name_prefix
  account_id              = data.aws_caller_identity.current.account_id
  aws_region              = var.aws_region
  frontend_index_html     = var.frontend_index_html
  document_retention_days = var.document_retention_days
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

  name_prefix                = local.name_prefix
  private_subnet_ids         = data.terraform_remote_state.l0.outputs.private_subnet_ids
  database_security_group_id = module.network_access.database_security_group_id
  db_name                    = var.db_name
  db_username                = var.db_username
  db_instance_class          = var.db_instance_class
  db_allocated_storage       = var.db_allocated_storage
  backup_retention_period    = var.db_backup_retention_period
  skip_final_snapshot        = var.db_skip_final_snapshot
}

module "network_access" {
  source = "./modules/network-access"

  name_prefix           = local.name_prefix
  vpc_id                = data.terraform_remote_state.l0.outputs.vpc_id
  alb_security_group_id = data.terraform_remote_state.l1.outputs.shared_alb_security_group_id
  container_port        = var.app_container_port
  aws_region            = var.aws_region
}

module "iam" {
  source = "./modules/iam"

  name_prefix                  = local.name_prefix
  sqs_queue_arn                = module.sqs.queue_arn
  document_bucket_arn          = module.storage.document_bucket_arn
  database_secret_arn          = module.rds.database_secret_arn
  bedrock_invoke_resource_arns = var.bedrock_invoke_resource_arns
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
  lambda_security_group_id  = module.network_access.lambda_security_group_id
  sqs_queue_arn             = module.sqs.queue_arn
  database_secret_arn       = module.rds.database_secret_arn
  database_name             = module.rds.db_name

  depends_on = [module.iam, module.vpc_endpoints]
}

check "queue_visibility_covers_lambda_retries" {
  assert {
    condition     = var.queue_visibility_timeout_seconds >= var.lambda_timeout_seconds * 6
    error_message = "queue_visibility_timeout_seconds must be at least six times lambda_timeout_seconds."
  }
}

module "ecs_service" {
  source = "./modules/ecs-service"

  name_prefix            = local.name_prefix
  environment            = local.environment
  vpc_id                 = data.terraform_remote_state.l0.outputs.vpc_id
  subnet_ids             = data.terraform_remote_state.l0.outputs.public_subnet_ids
  assign_public_ip       = true
  app_security_group_id  = module.network_access.app_security_group_id
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
  image_digest           = var.app_image_digest
  health_check_path      = var.health_check_path
  sqs_queue_url          = module.sqs.queue_url
  database_secret_arn    = module.rds.database_secret_arn
  database_name          = module.rds.db_name
  document_bucket_name   = module.storage.document_bucket_name
  api_key_secret_arn     = module.iam.api_key_secret_arn
  bedrock_model_id       = var.bedrock_model_id
}

module "vpc_endpoints" {
  source = "./modules/vpc-endpoints"

  name_prefix                               = local.name_prefix
  vpc_id                                    = data.terraform_remote_state.l0.outputs.vpc_id
  aws_region                                = var.aws_region
  private_subnet_ids                        = data.terraform_remote_state.l0.outputs.private_subnet_ids
  private_route_table_ids                   = data.terraform_remote_state.l0.outputs.private_route_table_ids
  secretsmanager_endpoint_security_group_id = module.network_access.secretsmanager_endpoint_security_group_id
  document_bucket_arn                       = module.storage.document_bucket_arn
  database_secret_arn                       = module.rds.database_secret_arn
  api_key_secret_arn                        = module.iam.api_key_secret_arn
}

module "cdn" {
  source = "./modules/cdn"

  name_prefix                          = local.name_prefix
  frontend_bucket_arn                  = module.storage.frontend_bucket_arn
  frontend_bucket_name                 = module.storage.frontend_bucket_name
  frontend_bucket_regional_domain_name = module.storage.frontend_bucket_regional_domain_name
  alb_dns_name                         = data.terraform_remote_state.l1.outputs.shared_alb_dns_name
  price_class                          = var.cloudfront_price_class
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
