variable "aws_region" {
  description = "The AWS region to deploy resources in."
  type        = string
  default     = "ap-southeast-2"
}

variable "allowed_account_id" {
  description = "The only AWS account in which this root module may operate."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.allowed_account_id))
    error_message = "allowed_account_id must be a 12-digit AWS account ID."
  }
}

variable "project_name" {
  description = "The name of the project. This will be used as a prefix for resource names."
  type        = string
  default     = "vantage-ai"
}

variable "owner" {
  description = "Owner tag used for cost attribution and cleanup accountability."
  type        = string
}

variable "expires_at" {
  description = "ISO-8601 date after which the ephemeral environment should be removed."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{4}-[0-9]{2}-[0-9]{2}$", var.expires_at))
    error_message = "expires_at must use YYYY-MM-DD."
  }
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
