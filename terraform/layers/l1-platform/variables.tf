variable "aws_region" {
  type    = string
  default = "ap-southeast-2"
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
  type    = string
  default = "vantage-ai"
}

variable "owner" {
  type = string
}

variable "expires_at" {
  type = string

  validation {
    condition     = can(regex("^[0-9]{4}-[0-9]{2}-[0-9]{2}$", var.expires_at))
    error_message = "expires_at must use YYYY-MM-DD."
  }
}

variable "log_retention_days" {
  type    = number
  default = 14
}

variable "application_port" {
  type    = number
  default = 8000
}

variable "state_bucket" {
  description = "S3 bucket containing lower-layer Terraform state."
  type        = string
}

variable "state_region" {
  description = "AWS region containing the Terraform state bucket."
  type        = string
}

variable "state_workspace_key_prefix" {
  description = "S3 backend workspace key prefix shared by every layer."
  type        = string
}
