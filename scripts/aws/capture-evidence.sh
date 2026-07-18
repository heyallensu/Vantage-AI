#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly REPO_ROOT
readonly L1_DIR="${REPO_ROOT}/terraform/layers/l1-platform"
readonly L2_DIR="${REPO_ROOT}/terraform/layers/l2-application/vantage-ai"
readonly EVIDENCE_DIR="${EVIDENCE_DIR:-${REPO_ROOT}/artifacts/portfolio-evidence}"

: "${API_BASE_URL:?API_BASE_URL is required}"
: "${DOCUMENT_ID:?DOCUMENT_ID is required}"

command -v aws >/dev/null 2>&1 || { printf 'aws is required\n' >&2; exit 1; }
command -v jq >/dev/null 2>&1 || { printf 'jq is required\n' >&2; exit 1; }
command -v terraform >/dev/null 2>&1 || { printf 'terraform is required\n' >&2; exit 1; }

mkdir -p "$EVIDENCE_DIR"

l2_outputs="$(terraform -chdir="$L2_DIR" output -json)"
ecs_cluster="$(jq -er '.ecs_cluster_name.value' <<<"$l2_outputs")"
ecs_service="$(jq -er '.ecs_service_name.value' <<<"$l2_outputs")"
lambda_function="$(jq -er '.lambda_function_name.value' <<<"$l2_outputs")"
database="$(jq -er '.db_identifier.value' <<<"$l2_outputs")"
distribution_id="$(jq -er '.cloudfront_distribution_id.value' <<<"$l2_outputs")"
queue_url="$(jq -er '.sqs_queue_url.value' <<<"$l2_outputs")"
log_group="$(terraform -chdir="$L1_DIR" output -raw ecs_platform_log_group_name)"

jq -n \
  --arg generated_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg commit_sha "${GITHUB_SHA:-$(git -C "$REPO_ROOT" rev-parse HEAD)}" \
  --arg api_base_url "$API_BASE_URL" \
  --arg document_id "$DOCUMENT_ID" \
  --arg image_tag "$(jq -er '.deployed_image_tag.value' <<<"$l2_outputs")" \
  --arg image_digest "$(jq -er '.deployed_image_digest.value' <<<"$l2_outputs")" \
  '{generated_at:$generated_at,environment:"portfolio",commit_sha:$commit_sha,api_base_url:$api_base_url,document_id:$document_id,image:{tag:$image_tag,digest:$image_digest}}' \
  >"${EVIDENCE_DIR}/deployment-summary.json"

aws ecs describe-services \
  --cluster "$ecs_cluster" \
  --services "$ecs_service" \
  --query 'services[0].{status:status,desired:desiredCount,running:runningCount,pending:pendingCount,deployments:length(deployments)}' \
  --output json >"${EVIDENCE_DIR}/ecs-service.json"

aws lambda get-function-configuration \
  --function-name "$lambda_function" \
  --query '{state:State,runtime:Runtime,version:Version,last_update_status:LastUpdateStatus,memory_mb:MemorySize,timeout_seconds:Timeout}' \
  --output json >"${EVIDENCE_DIR}/lambda-processor.json"

aws rds describe-db-instances \
  --db-instance-identifier "$database" \
  --query 'DBInstances[0].{status:DBInstanceStatus,engine:Engine,engine_version:EngineVersion,storage_encrypted:StorageEncrypted,multi_az:MultiAZ,publicly_accessible:PubliclyAccessible}' \
  --output json >"${EVIDENCE_DIR}/database.json"

aws cloudfront get-distribution \
  --id "$distribution_id" \
  --query 'Distribution.{status:Status,enabled:DistributionConfig.Enabled,http_version:DistributionConfig.HttpVersion,price_class:DistributionConfig.PriceClass}' \
  --output json >"${EVIDENCE_DIR}/cloudfront.json"

aws sqs get-queue-attributes \
  --queue-url "$queue_url" \
  --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible \
  --query 'Attributes' \
  --output json >"${EVIDENCE_DIR}/queue.json"

raw_logs="$(mktemp)"
trap 'rm -f "$raw_logs"' EXIT
aws logs filter-log-events \
  --log-group-name "$log_group" \
  --limit 50 \
  --query 'events[].message' \
  --output json >"$raw_logs"
jq '[.[] | fromjson? | select(.message == "request_completed") | {timestamp,level,route,method,status,duration_ms,request_id,document_id}]' \
  "$raw_logs" >"${EVIDENCE_DIR}/api-requests.json"

printf 'Sanitized deployment evidence captured in %s.\n' "$EVIDENCE_DIR"
