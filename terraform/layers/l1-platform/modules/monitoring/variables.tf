variable "name_prefix" {
  type = string
}

variable "log_retention_days" {
  type    = number
  default = 14
}

variable "ecs_cluster_name" {
  type = string
}
