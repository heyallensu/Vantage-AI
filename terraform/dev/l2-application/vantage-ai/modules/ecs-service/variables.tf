variable "name_prefix" {
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

variable "alb_security_group_id" {
  type = string
}

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

variable "image_tag" {
  type = string
}

variable "health_check_path" {
  type = string
}

variable "sqs_queue_url" {
  type = string
}

variable "database_url" {
  type      = string
  sensitive = true
}

variable "bedrock_model_id" {
  type = string
}
