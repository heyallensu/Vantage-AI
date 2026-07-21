#!/usr/bin/env bash
set -Eeuo pipefail

: "${AWS_ACCOUNT_ID:?AWS_ACCOUNT_ID is required}"
AWS_REGION="${AWS_REGION:-ap-southeast-2}"
CLEANUP_TIMEOUT_SECONDS="${CLEANUP_TIMEOUT_SECONDS:-900}"
CLEANUP_POLL_SECONDS="${CLEANUP_POLL_SECONDS:-30}"

command -v aws >/dev/null 2>&1 || { printf 'aws is required\n' >&2; exit 1; }
command -v jq >/dev/null 2>&1 || { printf 'jq is required\n' >&2; exit 1; }
[[ "$AWS_ACCOUNT_ID" =~ ^[0-9]{12}$ ]] || { printf 'Invalid AWS_ACCOUNT_ID.\n' >&2; exit 1; }
[[ "$CLEANUP_TIMEOUT_SECONDS" =~ ^[0-9]+$ ]] || { printf 'Invalid cleanup timeout.\n' >&2; exit 1; }
[[ "$CLEANUP_POLL_SECONDS" =~ ^[0-9]+$ ]] || { printf 'Invalid cleanup poll interval.\n' >&2; exit 1; }

actual_account="$(aws sts get-caller-identity --query Account --output text)"
[[ "$actual_account" == "$AWS_ACCOUNT_ID" ]] || {
  printf 'Refusing cleanup assertion outside the approved AWS account.\n' >&2
  exit 1
}

readonly PREFIX="vantage-ai-portfolio"
readonly DOCUMENT_BUCKET="${PREFIX}-${AWS_ACCOUNT_ID}-documents"
readonly FRONTEND_BUCKET="${PREFIX}-${AWS_ACCOUNT_ID}-frontend"

resource_exists() {
  local service="$1"
  shift
  "$service" "$@" >/dev/null 2>&1
}

remaining_resources() {
  local count=0
  local tagged
  tagged="$(aws resourcegroupstaggingapi get-resources \
    --tag-filters Key=Project,Values=vantage-ai Key=Environment,Values=portfolio \
    --resource-type-filters ec2 elasticloadbalancing ecs:service ecr:repository rds:db lambda:function sqs:queue cloudfront:distribution s3:bucket \
    --query 'length(ResourceTagMappingList)' \
    --output text)"
  [[ "$tagged" =~ ^[0-9]+$ ]] || tagged=1
  count=$((count + tagged))

  if resource_exists aws rds describe-db-instances --db-instance-identifier "${PREFIX}-postgres"; then count=$((count + 1)); fi
  if resource_exists aws lambda get-function --function-name "${PREFIX}-processor"; then count=$((count + 1)); fi
  if resource_exists aws ecr describe-repositories --repository-names "${PREFIX}-api"; then count=$((count + 1)); fi
  if resource_exists aws elbv2 describe-load-balancers --names "${PREFIX}-shared-alb"; then count=$((count + 1)); fi
  if resource_exists aws s3api head-bucket --bucket "$DOCUMENT_BUCKET"; then count=$((count + 1)); fi
  if resource_exists aws s3api head-bucket --bucket "$FRONTEND_BUCKET"; then count=$((count + 1)); fi

  local cluster_count
  cluster_count="$(aws ecs describe-clusters \
    --clusters "${PREFIX}-cluster" \
    --query "length(clusters[?status != 'INACTIVE'])" \
    --output text)"
  [[ "$cluster_count" =~ ^[0-9]+$ ]] || cluster_count=1
  count=$((count + cluster_count))

  printf '%s\n' "$count"
}

deadline=$((SECONDS + CLEANUP_TIMEOUT_SECONDS))
while true; do
  remaining="$(remaining_resources)"
  if [[ "$remaining" == "0" ]]; then
    printf 'Cleanup assertion passed: no portfolio runtime resources remain.\n'
    exit 0
  fi
  if ((SECONDS >= deadline)); then
    printf 'Cleanup assertion failed: %s portfolio resource checks still report active resources.\n' "$remaining" >&2
    exit 1
  fi
  printf 'Waiting for AWS deletion propagation; %s resource checks still active.\n' "$remaining"
  sleep "$CLEANUP_POLL_SECONDS"
done
