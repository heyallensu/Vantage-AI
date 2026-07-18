#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly REPO_ROOT
readonly ENV_DIR="${REPO_ROOT}/terraform/environments/portfolio"

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    printf 'Required command is unavailable: %s\n' "$1" >&2
    exit 1
  }
}

require_value() {
  local name="$1"
  [[ -n "${!name:-}" ]] || {
    printf 'Required environment variable is empty: %s\n' "$name" >&2
    exit 1
  }
}

require_command aws
require_command python3
require_command terraform

for name in AWS_ACCOUNT_ID TF_STATE_BUCKET BEDROCK_MODEL_ID BEDROCK_INFERENCE_PROFILE_ARN BEDROCK_FOUNDATION_MODEL_ARNS; do
  require_value "$name"
done

AWS_REGION="${AWS_REGION:-ap-southeast-2}"
PORTFOLIO_OWNER="${PORTFOLIO_OWNER:-${GITHUB_REPOSITORY_OWNER:-portfolio-owner}}"
PORTFOLIO_EXPIRES_AT="${PORTFOLIO_EXPIRES_AT:-$(python3 -c 'from datetime import date,timedelta; print(date.today()+timedelta(days=1))')}"

[[ "$AWS_ACCOUNT_ID" =~ ^[0-9]{12}$ ]] || {
  printf 'AWS_ACCOUNT_ID must contain exactly 12 digits.\n' >&2
  exit 1
}
[[ "$AWS_REGION" =~ ^[a-z]{2}(-gov)?-[a-z]+-[0-9]+$ ]] || {
  printf 'AWS_REGION is not a canonical AWS region.\n' >&2
  exit 1
}
[[ "$TF_STATE_BUCKET" =~ ^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$ ]] || {
  printf 'TF_STATE_BUCKET is not a valid S3 bucket name.\n' >&2
  exit 1
}
[[ "$PORTFOLIO_OWNER" =~ ^[A-Za-z0-9._@+-]{1,64}$ ]] || {
  printf 'PORTFOLIO_OWNER contains unsupported characters.\n' >&2
  exit 1
}
[[ "$PORTFOLIO_EXPIRES_AT" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || {
  printf 'PORTFOLIO_EXPIRES_AT must use YYYY-MM-DD.\n' >&2
  exit 1
}
[[ "$BEDROCK_MODEL_ID" =~ ^[A-Za-z0-9._:-]{1,200}$ ]] || {
  printf 'BEDROCK_MODEL_ID is invalid.\n' >&2
  exit 1
}
[[ "$BEDROCK_INFERENCE_PROFILE_ARN" =~ ^arn:(aws|aws-us-gov|aws-cn):bedrock:[a-z0-9-]+:${AWS_ACCOUNT_ID}:inference-profile/[^[:space:],]+$ ]] || {
  printf 'BEDROCK_INFERENCE_PROFILE_ARN must be an inference profile owned by the approved account.\n' >&2
  exit 1
}

IFS=',' read -r -a foundation_model_arns <<<"$BEDROCK_FOUNDATION_MODEL_ARNS"
(( ${#foundation_model_arns[@]} > 0 )) || {
  printf 'At least one Bedrock foundation model ARN is required.\n' >&2
  exit 1
}

bedrock_arns_hcl="  \"${BEDROCK_INFERENCE_PROFILE_ARN}\""
for raw_arn in "${foundation_model_arns[@]}"; do
  arn="${raw_arn#"${raw_arn%%[![:space:]]*}"}"
  arn="${arn%"${arn##*[![:space:]]}"}"
  [[ "$arn" =~ ^arn:(aws|aws-us-gov|aws-cn):bedrock:[a-z0-9-]+::foundation-model/[^[:space:],]+$ ]] || {
    printf 'Invalid Bedrock foundation model ARN: %s\n' "$arn" >&2
    exit 1
  }
  printf -v bedrock_arns_hcl '%s,\n  "%s"' "$bedrock_arns_hcl" "$arn"
done

actual_account="$(aws sts get-caller-identity --query Account --output text)"
[[ "$actual_account" == "$AWS_ACCOUNT_ID" ]] || {
  printf 'Refusing to continue: AWS caller account does not match AWS_ACCOUNT_ID.\n' >&2
  exit 1
}

umask 077
printf '%s\n' "$AWS_ACCOUNT_ID" >"${REPO_ROOT}/.aws-account-id"

write_backend() {
  local layer_key="$1"
  local destination="$2"
  {
    printf 'bucket               = "%s"\n' "$TF_STATE_BUCKET"
    printf 'key                  = "%s/terraform.tfstate"\n' "$layer_key"
    printf 'region               = "%s"\n' "$AWS_REGION"
    printf 'encrypt              = true\n'
    printf 'use_lockfile          = true\n'
    printf 'workspace_key_prefix = "vantage-ai"\n'
    printf 'allowed_account_ids   = ["%s"]\n' "$AWS_ACCOUNT_ID"
  } >"$destination"
}

write_backend "l0-foundation" "${ENV_DIR}/l0-foundation.backend.hcl"
write_backend "l1-platform" "${ENV_DIR}/l1-platform.backend.hcl"
write_backend "l2-application/vantage-ai" "${ENV_DIR}/l2-application-vantage-ai.backend.hcl"

{
  printf 'aws_region   = "%s"\n' "$AWS_REGION"
  printf 'project_name = "vantage-ai"\n'
  printf 'owner        = "%s"\n' "$PORTFOLIO_OWNER"
  printf 'expires_at   = "%s"\n\n' "$PORTFOLIO_EXPIRES_AT"
  printf 'vpc_cidr            = "10.20.0.0/16"\n'
  printf 'public_subnet_cidrs  = ["10.20.0.0/24", "10.20.1.0/24"]\n'
  printf 'private_subnet_cidrs = ["10.20.10.0/24", "10.20.11.0/24"]\n'
} >"${ENV_DIR}/l0-foundation.tfvars"

{
  printf 'aws_region         = "%s"\n' "$AWS_REGION"
  printf 'project_name       = "vantage-ai"\n'
  printf 'owner              = "%s"\n' "$PORTFOLIO_OWNER"
  printf 'expires_at         = "%s"\n' "$PORTFOLIO_EXPIRES_AT"
  printf 'log_retention_days = 14\n'
  printf 'application_port   = 8000\n\n'
  printf 'state_bucket               = "%s"\n' "$TF_STATE_BUCKET"
  printf 'state_region               = "%s"\n' "$AWS_REGION"
  printf 'state_workspace_key_prefix = "vantage-ai"\n'
} >"${ENV_DIR}/l1-platform.tfvars"

{
  printf 'aws_region   = "%s"\n' "$AWS_REGION"
  printf 'project_name = "vantage-ai"\n'
  printf 'app_name     = "vantage-ai"\n'
  printf 'owner        = "%s"\n' "$PORTFOLIO_OWNER"
  printf 'expires_at   = "%s"\n\n' "$PORTFOLIO_EXPIRES_AT"
  printf 'state_bucket               = "%s"\n' "$TF_STATE_BUCKET"
  printf 'state_region               = "%s"\n' "$AWS_REGION"
  printf 'state_workspace_key_prefix = "vantage-ai"\n\n'
  printf 'queue_visibility_timeout_seconds = 360\n'
  printf 'queue_message_retention_seconds  = 345600\n'
  printf 'queue_max_receive_count          = 5\n\n'
  printf 'db_name                    = "vantage"\n'
  printf 'db_username                = "vantage"\n'
  printf 'db_instance_class          = "db.t4g.micro"\n'
  printf 'db_allocated_storage       = 20\n'
  printf 'db_backup_retention_period = 1\n'
  printf 'db_deletion_protection     = false\n'
  printf 'db_skip_final_snapshot     = true\n\n'
  printf 'lambda_runtime      = "python3.12"\n'
  printf 'lambda_handler      = "handler.handler"\n'
  printf 'lambda_timeout_seconds = 60\n'
  printf 'lambda_memory_size     = 256\n'
  printf 'lambda_package_path    = "../../../../lambda/processor/package.zip"\n\n'
  printf 'app_container_port = 8000\n'
  printf 'app_desired_count  = 1\n'
  printf 'app_cpu            = 256\n'
  printf 'app_memory         = 512\n'
  printf 'app_image_tag       = "000000000000"\n'
  printf 'app_image_digest    = "sha256:0000000000000000000000000000000000000000000000000000000000000000"\n'
  printf 'health_check_path   = "/health"\n'
  printf 'bedrock_model_id    = "%s"\n' "$BEDROCK_MODEL_ID"
  printf 'bedrock_invoke_resource_arns = [\n%s,\n]\n' "$bedrock_arns_hcl"
  printf 'cloudfront_price_class  = "PriceClass_100"\n'
  printf 'document_retention_days = 7\n\n'
  printf 'alarm_actions                 = []\n'
  printf 'lambda_error_threshold        = 1\n'
  printf 'dlq_visible_messages_threshold = 1\n'
} >"${ENV_DIR}/l2-application-vantage-ai.tfvars"

terraform fmt \
  "${ENV_DIR}/l0-foundation.tfvars" \
  "${ENV_DIR}/l1-platform.tfvars" \
  "${ENV_DIR}/l2-application-vantage-ai.tfvars" >/dev/null

printf 'Preflight passed for the approved AWS account and portfolio configuration.\n'
