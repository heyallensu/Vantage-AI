variable "aws_region" {
  description = "The AWS region to deploy resources in."
  type        = string
  default     = "ap-southeast-2"
}

variable "project_name" {
  description = "The name of the project. This will be used as a prefix for resource names."
  type        = string
  default     = "vantage-ai"
}

variable "environment" {
  description = "The deployment environment (e.g., dev, staging, prod). This will be used as a suffix for resource names."
  type        = string
  default     = "dev"
}

variable "vpc_cidr" {
  description = "The CIDR block for the VPC."
  type        = string
  default     = "10.20.0.0/16"
}

variable "public_subnet_cidrs" {
  type    = list(string)
  default = ["10.20.0.0/24", "10.20.1.0/24"]
}

variable "private_subnet_cidrs" {
  type    = list(string)
  default = ["10.20.10.0/24", "10.20.11.0/24"]
}
