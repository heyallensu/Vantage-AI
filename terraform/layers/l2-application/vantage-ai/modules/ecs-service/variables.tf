variable "name_prefix" {
  type = string
}

variable "environment" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "subnet_ids" {
  type = list(string)
}

variable "assign_public_ip" {
  type = bool
}

variable "app_security_group_id" { type = string }

variable "shared_listener_arn" {
  type = string
}

variable "ecs_cluster_id" {
  type = string
}

variable "ecr_repository_url" {
  type = string
}

variable "log_group_name" {
  type = string
}

variable "ecs_execution_role_arn" {
  type = string
}

variable "ecs_task_role_arn" {
  type = string
}

variable "container_port" {
  type = number
}

variable "desired_count" {
  type = number
}

variable "cpu" {
  type = number
}

variable "memory" {
  type = number
}

variable "image_digest" {
  type = string

  validation {
    condition     = can(regex("^sha256:[0-9a-f]{64}$", var.image_digest))
    error_message = "image_digest must be a canonical sha256 ECR digest."
  }
}

variable "health_check_path" {
  type = string
}

variable "sqs_queue_url" {
  type = string
}

variable "database_secret_arn" { type = string }
variable "database_name" { type = string }
variable "document_bucket_name" { type = string }
variable "api_key_secret_arn" { type = string }

variable "bedrock_model_id" {
  type = string
}
