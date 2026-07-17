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

variable "owner" {
  type = string
}

variable "expires_at" {
  type = string

  validation {
    condition     = can(regex("^[0-9]{4}-[0-9]{2}-[0-9]{2}$", var.expires_at))
    error_message = "expires_at must use YYYY-MM-DD."
  }
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
  default = 360
}

variable "queue_message_retention_seconds" {
  type    = number
  default = 345600
}

variable "queue_max_receive_count" {
  type    = number
  default = 5
}

variable "db_name" {
  type    = string
  default = "vantage"
}

variable "db_username" {
  type    = string
  default = "vantage"
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
  description = "Portfolio-only teardown switch. True is intentional because the demo contains disposable sample data and must auto-destroy."
  type        = bool
  default     = true
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

  validation {
    condition     = var.app_desired_count == 1
    error_message = "The low-cost portfolio environment runs exactly one ECS task."
  }
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
  description = "Immutable Git commit SHA used as the ECR image tag."
  type        = string

  validation {
    condition     = var.app_image_tag != "latest" && can(regex("^[0-9a-f]{7,40}$", var.app_image_tag))
    error_message = "app_image_tag must be a 7-40 character lowercase Git SHA and must not be latest."
  }
}

variable "app_image_digest" {
  description = "Trusted immutable ECR digest pinned into the ECS task definition."
  type        = string

  validation {
    condition     = can(regex("^sha256:[0-9a-f]{64}$", var.app_image_digest))
    error_message = "app_image_digest must be a canonical sha256 ECR digest."
  }
}

variable "health_check_path" {
  type    = string
  default = "/health"
}

variable "bedrock_model_id" {
  type    = string
  default = "anthropic.claude-haiku-20240307-v1:0"
}

variable "bedrock_invoke_resource_arns" {
  description = "Exact inference-profile and destination foundation-model ARNs allowed for Bedrock invocation."
  type        = list(string)

  validation {
    condition = (
      length(var.bedrock_invoke_resource_arns) >= 2 &&
      anytrue([for arn in var.bedrock_invoke_resource_arns : can(regex(":inference-profile/", arn))]) &&
      anytrue([for arn in var.bedrock_invoke_resource_arns : can(regex(":foundation-model/", arn))]) &&
      alltrue([
        for arn in var.bedrock_invoke_resource_arns :
        can(regex("^arn:(aws|aws-us-gov|aws-cn):bedrock:[a-z0-9-]+:([0-9]{12})?:(inference-profile|foundation-model)/[^[:space:]]+$", arn))
      ])
    )
    error_message = "bedrock_invoke_resource_arns must contain exact inference-profile and destination foundation-model ARNs."
  }
}

variable "document_retention_days" {
  type    = number
  default = 7

  validation {
    condition     = var.document_retention_days >= 1
    error_message = "document_retention_days must be at least one day."
  }
}

variable "cloudfront_price_class" {
  type    = string
  default = "PriceClass_100"

  validation {
    condition     = contains(["PriceClass_100", "PriceClass_200", "PriceClass_All"], var.cloudfront_price_class)
    error_message = "cloudfront_price_class must be a supported CloudFront price class."
  }
}

variable "frontend_index_html" {
  description = "Small static landing page stored in the private frontend bucket."
  type        = string
  default     = <<-HTML
    <!doctype html><html lang="en"><meta charset="utf-8"><title>Vantage AI</title><main><h1>Vantage AI</h1><p>Intelligent document processing portfolio environment.</p><p><a href="/docs">Open API documentation</a></p></main></html>
  HTML
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
