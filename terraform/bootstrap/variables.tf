variable "aws_region" {
  description = "AWS region in which to create the state bucket and deployment role."
  type        = string
  default     = "ap-southeast-2"
}

variable "allowed_account_id" {
  description = "The only AWS account in which the bootstrap stack may operate."
  type        = string
  sensitive   = true

  validation {
    condition     = can(regex("^[0-9]{12}$", var.allowed_account_id))
    error_message = "allowed_account_id must be a 12-digit AWS account ID."
  }
}

variable "github_owner" {
  description = "GitHub organization or user that owns the deployment repository."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9][A-Za-z0-9-]{0,38}$", var.github_owner))
    error_message = "github_owner must be a valid GitHub organization or user name."
  }
}

variable "github_owner_id" {
  description = "Immutable numeric GitHub ID for the organization or user that owns the repository."
  type        = string

  validation {
    condition     = can(regex("^[0-9]+$", var.github_owner_id))
    error_message = "github_owner_id must contain only digits."
  }
}

variable "github_repository" {
  description = "GitHub repository allowed to assume the deployment role."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9._-]+$", var.github_repository))
    error_message = "github_repository must contain only characters accepted in a GitHub repository name."
  }
}

variable "github_repository_id" {
  description = "Immutable numeric GitHub repository ID used by the customized OIDC subject template."
  type        = string

  validation {
    condition     = can(regex("^[0-9]+$", var.github_repository_id))
    error_message = "github_repository_id must contain only digits."
  }
}

variable "state_bucket_unique_suffix" {
  description = "Globally unique lowercase suffix for the state bucket and bootstrap role."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9](?:[a-z0-9-]{1,23}[a-z0-9])$", var.state_bucket_unique_suffix))
    error_message = "state_bucket_unique_suffix must be 3-25 lowercase letters, digits, or internal hyphens, and must end with a letter or digit."
  }
}

variable "state_bucket_name_prefix" {
  description = "Stable prefix used before the required unique state bucket suffix."
  type        = string
  default     = "vantage-ai-terraform-state"
}

variable "project_name" {
  description = "Project prefix used to scope the GitHub deployment role permissions."
  type        = string
  default     = "vantage-ai"
}
