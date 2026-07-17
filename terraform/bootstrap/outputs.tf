output "state_bucket_name" {
  description = "S3 bucket to use in each layer backend configuration."
  value       = aws_s3_bucket.terraform_state.id
}

output "state_bucket_region" {
  description = "Region to use in each layer backend configuration."
  value       = var.aws_region
}

output "github_oidc_provider_arn" {
  description = "Repository-scoped GitHub Actions OIDC provider ARN."
  value       = aws_iam_openid_connect_provider.github_actions.arn
}

output "github_deploy_role_arn" {
  description = "Role ARN for the repository deployment workflow."
  value       = aws_iam_role.github_deploy.arn
}
