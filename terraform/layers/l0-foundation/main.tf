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

module "vpc" {
  source = "./modules/vpc"

  name_prefix          = local.name_prefix
  vpc_cidr             = var.vpc_cidr
  public_subnet_cidrs  = var.public_subnet_cidrs
  private_subnet_cidrs = var.private_subnet_cidrs
  enable_nat_gateway   = var.enable_nat_gateway
}

module "security_baseline" {
  source = "./modules/security-baseline"

  vpc_id      = module.vpc.vpc_id
  name_prefix = local.name_prefix
}
