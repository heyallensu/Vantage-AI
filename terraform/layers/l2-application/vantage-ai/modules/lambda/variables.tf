variable "name_prefix" {
  type = string
}

variable "lambda_package_path" {
  type = string
}

variable "lambda_runtime" {
  type = string
}

variable "lambda_handler" {
  type = string
}

variable "lambda_timeout_seconds" {
  type = number
}

variable "lambda_memory_size" {
  type = number
}

variable "lambda_execution_role_arn" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "lambda_security_group_id" { type = string }

variable "sqs_queue_arn" {
  type = string
}

variable "database_secret_arn" { type = string }
variable "database_name" { type = string }
