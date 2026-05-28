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

module "ecs_cluster" {
  source = "./modules/ecs-cluster"

  name_prefix = local.name_prefix
}

module "ecr" {
  source = "./modules/ecr"

  name_prefix = local.name_prefix
}
