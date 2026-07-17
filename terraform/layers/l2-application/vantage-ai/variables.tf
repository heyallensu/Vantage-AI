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

variable "app_name" {
  type    = string
  default = "vantage-ai"
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

variable "queue_visibility_timeout_seconds" {
  type    = number
  default = 120
}

variable "queue_message_retention_seconds" {
  type    = number
  default = 345600
}

variable "queue_max_receive_count" {
  type    = number
  default = 3
}

variable "db_name" {
  type    = string
  default = "vantage"
}

variable "db_username" {
  type    = string
  default = "vantage"
}

variable "db_password" {
  type      = string
  sensitive = true
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "db_allocated_storage" {
  type    = number
  default = 20
}

variable "db_backup_retention_period" {
  type    = number
  default = 1
}

variable "db_skip_final_snapshot" {
  type    = bool
  default = true
}

variable "lambda_runtime" {
  type    = string
  default = "python3.12"
}

variable "lambda_handler" {
  type    = string
  default = "handler.handler"
}

variable "lambda_timeout_seconds" {
  type    = number
  default = 60
}

variable "lambda_memory_size" {
  type    = number
  default = 256
}

variable "lambda_package_path" {
  type    = string
  default = "../../../../lambda/processor/package.zip"
}

variable "app_container_port" {
  type    = number
  default = 8000
}

variable "app_desired_count" {
  type    = number
  default = 1
}

variable "app_cpu" {
  type    = number
  default = 256
}

variable "app_memory" {
  type    = number
  default = 512
}

variable "app_image_tag" {
  type    = string
  default = "latest"
}

variable "health_check_path" {
  type    = string
  default = "/health"
}

variable "bedrock_model_id" {
  type    = string
  default = "anthropic.claude-haiku-20240307-v1:0"
}

variable "alarm_actions" {
  type    = list(string)
  default = []
}


variable "lambda_error_threshold" {
  type    = number
  default = 1
}

variable "dlq_visible_messages_threshold" {
  type    = number
  default = 0
}
