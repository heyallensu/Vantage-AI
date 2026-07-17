variable "name_prefix" {
  type = string
}

variable "sqs_queue_arn" {
  type = string
}

variable "document_bucket_arn" { type = string }
variable "database_secret_arn" { type = string }
variable "bedrock_invoke_resource_arns" { type = list(string) }
