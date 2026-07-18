#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly REPO_ROOT
readonly EVIDENCE_DIR="${EVIDENCE_DIR:-${REPO_ROOT}/artifacts/portfolio-evidence}"
readonly SAMPLE_FILE="${SAMPLE_FILE:-${REPO_ROOT}/sample-data.csv}"

: "${API_BASE_URL:?API_BASE_URL is required}"
: "${API_KEY_SECRET_NAME:?API_KEY_SECRET_NAME is required}"

command -v aws >/dev/null 2>&1 || { printf 'aws is required\n' >&2; exit 1; }
command -v curl >/dev/null 2>&1 || { printf 'curl is required\n' >&2; exit 1; }
command -v jq >/dev/null 2>&1 || { printf 'jq is required\n' >&2; exit 1; }
[[ -s "$SAMPLE_FILE" ]] || { printf 'Sample CSV is missing.\n' >&2; exit 1; }

API_BASE_URL="${API_BASE_URL%/}"
[[ "$API_BASE_URL" =~ ^https://[^/]+$ ]] || {
  printf 'API_BASE_URL must be an HTTPS origin without a path.\n' >&2
  exit 1
}

mkdir -p "$EVIDENCE_DIR"

api_key="$(aws secretsmanager get-secret-value \
  --secret-id "$API_KEY_SECRET_NAME" \
  --query SecretString \
  --output text)"
[[ -n "$api_key" && "$api_key" != "None" ]] || {
  printf 'Unable to resolve the ephemeral API key.\n' >&2
  exit 1
}

wait_for_endpoint() {
  local path="$1"
  local expected_status="$2"
  local attempts="${3:-90}"
  local response
  for ((attempt = 1; attempt <= attempts; attempt++)); do
    if response="$(curl --fail --silent --show-error --max-time 10 "${API_BASE_URL}${path}" 2>/dev/null)" &&
      jq -e --arg status "$expected_status" '.status == $status' <<<"$response" >/dev/null; then
      return 0
    fi
    sleep 10
  done
  printf 'Timed out waiting for %s.\n' "$path" >&2
  return 1
}

wait_for_endpoint "/health" "ok"
wait_for_endpoint "/ready" "ready"

upload_response="$(curl --fail --silent --show-error --max-time 30 \
  --request POST "${API_BASE_URL}/documents/upload" \
  --header "X-API-Key: ${api_key}" \
  --form "file=@${SAMPLE_FILE};type=text/csv")"
document_id="$(jq -er '.document_id' <<<"$upload_response")"
[[ "$document_id" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$ ]] || {
  printf 'Upload returned an invalid document identifier.\n' >&2
  exit 1
}

status="pending"
for ((attempt = 1; attempt <= 24; attempt++)); do
  status_response="$(curl --fail --silent --show-error --max-time 15 \
    --header "X-API-Key: ${api_key}" \
    "${API_BASE_URL}/documents/${document_id}/status")"
  status="$(jq -er '.status' <<<"$status_response")"
  case "$status" in
    completed) break ;;
    failed)
      printf 'The asynchronous document processor reported failure.\n' >&2
      exit 1
      ;;
    pending|processing) sleep 5 ;;
    *)
      printf 'Unexpected document status: %s\n' "$status" >&2
      exit 1
      ;;
  esac
done
[[ "$status" == "completed" ]] || {
  printf 'Document processing did not complete within 120 seconds.\n' >&2
  exit 1
}

records_response="$(curl --fail --silent --show-error --max-time 15 \
  --header "X-API-Key: ${api_key}" \
  "${API_BASE_URL}/records?document_id=${document_id}")"
record_count="$(jq -er 'length' <<<"$records_response")"
[[ "$record_count" == "10" ]] || {
  printf 'Expected 10 extracted records; received %s.\n' "$record_count" >&2
  exit 1
}

analysis_response="$(curl --fail --silent --show-error --max-time 60 \
  --request POST \
  --header "X-API-Key: ${api_key}" \
  "${API_BASE_URL}/insights/analyze?document_id=${document_id}")"
jq -e '(.record_count | type == "number") and (.summary | type == "string" and length > 0) and (.anomalies | type == "array")' \
  <<<"$analysis_response" >/dev/null

summary_response="$(curl --fail --silent --show-error --max-time 60 \
  --header "X-API-Key: ${api_key}" \
  "${API_BASE_URL}/insights/summary?document_id=${document_id}")"
jq -e '.summary | type == "string" and length > 0' <<<"$summary_response" >/dev/null

anomalies_response="$(curl --fail --silent --show-error --max-time 60 \
  --header "X-API-Key: ${api_key}" \
  "${API_BASE_URL}/insights/anomalies?document_id=${document_id}")"
jq -e '.anomalies | type == "array"' <<<"$anomalies_response" >/dev/null

jq -n \
  --arg document_id "$document_id" \
  --arg status "$status" \
  --argjson record_count "$record_count" \
  '{document_id:$document_id,status:$status,record_count:$record_count,bedrock:{analyze:true,summary:true,anomalies:true}}' \
  >"${EVIDENCE_DIR}/e2e-summary.json"

if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  printf 'document_id=%s\n' "$document_id" >>"$GITHUB_OUTPUT"
  printf 'api_base_url=%s\n' "$API_BASE_URL" >>"$GITHUB_OUTPUT"
fi

printf 'E2E verification passed: document completed with 10 records and all Bedrock routes responded.\n'
