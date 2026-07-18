variable "name_prefix" {
  type = string

  validation {
    condition     = can(regex("^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$", var.name_prefix))
    error_message = "name_prefix must contain only lowercase letters, digits, and internal hyphens."
  }
}

variable "account_id" {
  type = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.account_id))
    error_message = "account_id must be a 12-digit AWS account ID."
  }
}

variable "aws_region" {
  type = string

  validation {
    condition     = can(regex("^[a-z]{2}(?:-gov)?-[a-z]+-[0-9]+$", var.aws_region))
    error_message = "aws_region must be a canonical AWS region name."
  }
}
variable "frontend_index_html" { type = string }
variable "document_retention_days" {
  type = number

  validation {
    condition     = var.document_retention_days >= 1
    error_message = "document_retention_days must be at least one day."
  }
}
