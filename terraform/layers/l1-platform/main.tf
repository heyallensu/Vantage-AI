terraform {
  required_version = ">= 1.10.0"

  backend "s3" {}

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~>5.0"
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

module "ecs_cluster" {

  source = "./modules/ecs-cluster"

  name_prefix = local.name_prefix
}

module "ecr" {
  source = "./modules/ecr"

  name_prefix = local.name_prefix
}

module "shared_alb" {
  source = "./modules/shared-alb"

  name_prefix       = local.name_prefix
  vpc_id            = data.terraform_remote_state.l0.outputs.vpc_id
  vpc_cidr          = data.terraform_remote_state.l0.outputs.vpc_cidr
  public_subnet_ids = data.terraform_remote_state.l0.outputs.public_subnet_ids
  application_port  = var.application_port
}

module "monitoring" {
  source = "./modules/monitoring"

  name_prefix        = local.name_prefix
  log_retention_days = var.log_retention_days
  ecs_cluster_name   = module.ecs_cluster.cluster_name
}
