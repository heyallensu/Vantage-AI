variable "name_prefix" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "db_name" {
  type = string
}

variable "db_username" {
  type = string
}

variable "database_security_group_id" { type = string }

variable "db_instance_class" {
  type = string
}

variable "db_allocated_storage" {
  type = number
}

variable "backup_retention_period" {
  type = number
}

variable "skip_final_snapshot" {
  type = bool
}
