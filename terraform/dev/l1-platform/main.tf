terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~>5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

locals {
  environment = terraform.workspace == "default" ? var.environment : terraform.workspace
  name_prefix = "${var.project_name}-${local.environment}"
}

data "terraform_remote_state" "l0" {
  backend = "local"

  config = {
    path = "../l0-foundation/terraform.tfstate.d/dev/terraform.tfstate"
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
  public_subnet_ids = data.terraform_remote_state.l0.outputs.public_subnet_ids
}

module "monitoring" {
  source = "./modules/monitoring"

  name_prefix        = local.name_prefix
  log_retention_days = var.log_retention_days
}