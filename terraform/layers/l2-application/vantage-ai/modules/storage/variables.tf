variable "name_prefix" { type = string }
variable "account_id" { type = string }
variable "frontend_index_html" { type = string }
variable "document_retention_days" {
  type = number

  validation {
    condition     = var.document_retention_days >= 1
    error_message = "document_retention_days must be at least one day."
  }
}
