variable "aws_region" {
  type    = string
  default = "ap-southeast-2"
}

variable "project_name" {
  type    = string
  default = "vantage-ai"
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "log_retention_days" {
  type    = number
  default = 14
}