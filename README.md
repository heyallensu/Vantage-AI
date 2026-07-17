# Vantage-AI

An Intelligent Document Processing Platform — upload CSV documents, extract records asynchronously, and get AI-powered insights via Amazon Bedrock.

## Architecture

```
Client ──HTTPS──→ CloudFront ──OAC──→ private frontend S3
                       │
                       └──HTTP──→ ALB ──→ ECS Fargate (FastAPI)
                                      │       │       │
                                      │       │       └──→ Bedrock
                                      │       └──→ private document S3
                                      └──→ SQS + DLQ ──→ Lambda ──→ RDS
```

| Component | Technology |
|---|---|
| API | FastAPI (Python 3.12), Uvicorn |
| Database | PostgreSQL 16 (RDS) |
| Edge | CloudFront default HTTPS domain, private S3 origin with OAC, ALB API origin |
| Source Storage | Amazon S3 (private, encrypted, versioned, 7-day document retention, destroy-safe) |
| Message Queue | Amazon SQS + DLQ |
| Async Processing | AWS Lambda (VPC-attached) |
| AI Analysis | Amazon Bedrock — Claude Haiku 4.5 (Inference Profile) |
| Container Runtime | ECS Fargate |
| Load Balancer | HTTP ALB reachable only from the CloudFront origin-facing prefix list |
| Infra as Code | Terraform (3 layers: Foundation → Platform → Application) |
| Operations | CloudWatch log retention, alarms, and a low-cost operations dashboard |
| CI/CD | GitHub Actions (OIDC) and immutable Git-SHA ECR tags |

## Data Flow

1. **Upload** — Client POSTs a CSV to `/documents/upload`
2. **Store and queue** — API validates the file, stores it in S3, and publishes a versioned job containing its object key and SHA-256 checksum
3. **Process** — Lambda verifies the checksum and idempotently replaces the extracted `Record` rows in RDS
4. **Query** — Client polls `/documents/{id}/status` then fetches `/records`
5. **Analyze** — Client calls `/insights/analyze` — API sends records to Bedrock for AI summary + anomaly detection

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness check (public) |
| `GET` | `/ready` | Database readiness check (public) |
| `POST` | `/documents/upload` | Upload CSV (multipart form, API key required) |
| `GET` | `/documents/{id}/status` | Check processing status |
| `GET` | `/records` | List extracted records (filter by `document_id`, `category`) |
| `GET` | `/records/{id}` | Single record |
| `POST` | `/insights/analyze` | Full AI analysis (totals, categories, summary, anomalies) |
| `GET` | `/insights/summary` | Plain-English summary |
| `GET` | `/insights/anomalies` | AI-flagged anomalies |
| `GET` | `/docs` | Swagger UI (local only) |

## Quick Start — Local Development

```bash
# 1. Start API + PostgreSQL
make dev

API_KEY=local-development-only

# 2. Health check
curl http://localhost:8000/health

# 3. Upload sample CSV
curl -X POST http://localhost:8000/documents/upload \
  -H "X-API-Key: $API_KEY" \
  -F "file=@sample-data.csv"

# 4. Check status (document processes instantly in local mode)
curl -H "X-API-Key: $API_KEY" http://localhost:8000/documents/<DOC_ID>/status

# 5. View records
curl -H "X-API-Key: $API_KEY" \
  "http://localhost:8000/records?document_id=<DOC_ID>"

# 6. Stop
make down
```

> **Note:** Local mode (`ENV=local`) uses in-memory document storage and processes CSV inline without SQS/Lambda. Bedrock calls still require valid AWS credentials. The local API key is deliberately non-secret and must never be reused outside local development.

The API container runs as UID/GID `10001` with `HOME=/home/vantage`. Compose
mounts the host AWS directory read-only at `/home/vantage/.aws` and explicitly
sets `AWS_SHARED_CREDENTIALS_FILE` and `AWS_CONFIG_FILE` to files below that
non-root home; credentials are never mounted below `/root`.

## Runtime Security and Configuration

All document, record, and insight endpoints require the `X-API-Key` header. The API uses a timing-safe comparison and never includes the key in its structured logs. `/health` and `/ready` stay public for load-balancer probes.

Non-local startup fails immediately unless these values are present:

- `API_KEY`
- `AWS_DEFAULT_REGION`
- either `DATABASE_URL` or `DB_SECRET_ARN` (`DB_NAME` defaults to `vantage`)
- `DOCUMENT_BUCKET`
- `SQS_QUEUE_URL`

Use [.env.example](.env.example) only as a local template. RDS owns the production
master password in Secrets Manager. ECS and Lambda receive only its ARN and
assemble the PostgreSQL URL at runtime.

## Deployment — AWS

### Prerequisites

- A personally controlled, isolated AWS account with reviewed short-lived credentials
- Terraform ≥ 1.10.0 (required for native S3 state locking)
- Docker (with BuildKit for `linux/amd64` cross-build)
- A GitHub repository whose owner/name will be bound into the OIDC trust policy

This repository supports only the ephemeral `portfolio` environment. The safety
contract is plan → apply → capture evidence → destroy within one short validation
window. No real account IDs, backend coordinates, passwords, or repository values
belong in Git.

Every deployment transaction first verifies the active STS account against the
ignored `.aws-account-id`, then checks that L0, L1, and L2 each report the exact
`portfolio` workspace. A failure or empty response stops before Terraform plan,
apply, destroy, output, or ECR access. The workflow never switches workspaces;
run `make tf-workspace` explicitly, review the result, and retry. The verified
account and workspace are bound into local provenance and every saved-plan
manifest.

### Step 1 — Bootstrap state and OIDC once

```bash
# Local files below are ignored. Replace every placeholder before use.
cp terraform/bootstrap/terraform.tfvars.example terraform/bootstrap/terraform.tfvars
printf '%s\n' '<your-12-digit-account-id>' > .aws-account-id

# Creates the protected S3 state bucket and repository-scoped GitHub OIDC role.
# Terraform prompts for confirmation; review it before accepting.
make bootstrap
```

The bootstrap stack deliberately retains local state. Store
`terraform/bootstrap/bootstrap.tfstate` securely. Use its outputs to populate
the ignored backend and environment files described in
[terraform/environments/portfolio/README.md](terraform/environments/portfolio/README.md).

### Step 2 — Bind deployment artifacts to one commit

```bash
# Uses no AWS credentials or backend; a cold provider cache still downloads
# providers from the Terraform registry.
make tf-check

make tf-init
make tf-workspace

# Deploy only committed content. IMAGE_TAG defaults to this commit's canonical
# 12-character Git abbreviation and cannot be replaced by arbitrary hex.
export DEPLOY_COMMIT=HEAD

# Create, inspect, and apply one saved plan at a time.
make tf-plan-l0
terraform show .tfplans/portfolio/l0-foundation.tfplan
make tf-apply-l0

make tf-plan-l1
terraform show .tfplans/portfolio/l1-platform.tfplan
make tf-apply-l1

# L2 planning first ensures the immutable ECR image, then packages Lambda from
# the same Git commit, and records the package checksum in plan metadata.
make tf-plan-l2 DEPLOY_COMMIT="$DEPLOY_COMMIT"
terraform show .tfplans/portfolio/l2-application-vantage-ai.tfplan
make tf-apply-l2 DEPLOY_COMMIT="$DEPLOY_COMMIT"
```

Every saved plan has a SHA-256 manifest. Apply verifies that manifest before it
invokes Terraform, so even a one-byte plan change fails closed. `tf-apply-l2`
also refuses to continue if the commit, image tag, verified ECR digest, or
Lambda package checksum differs from the saved transaction. `.tfplans/` is
ignored because plans can contain sensitive values. Remove those local plans
after the validation window.

The API image is built from `git archive DEPLOY_COMMIT`, not the working tree,
and carries `org.opencontainers.image.revision=<full SHA>`. Uncommitted changes
are deliberately excluded—commit them before choosing the deployment commit.

### Immutable image retries

`.tfplans/portfolio/deployment-provenance.json` is the single-owner local trust
root for a deployment transaction. It records the full commit, canonical tag,
region, repository, and ECR-reported digest. Keep the ignored directory under
the deployer's exclusive control; cloud labels alone are not a trust root.

`make ensure-image` queries the SHA tag before publishing:

- a missing tag is built from the Git archive and pushed once;
- an existing tag is reused only when its ECR digest matches trusted local
  metadata and the pulled `RepoDigest` and revision label match that digest and
  the full deployment commit;
- authentication, network, unknown-tag, pull, inspection, and revision mismatch
  errors fail closed and never fall through to a push.

ECS receives `repository@sha256:...`, never a mutable tag reference. If the
local provenance file is lost after its tag exists, reuse fails closed. Start a
new transaction from a new commit, or perform an explicit controlled recovery
that independently re-establishes and reviews the trusted digest; the workflow
never reconstructs trust automatically from the image label.

After a transient failure, repair credentials/network and rerun the same target.
Never delete or retag an immutable image to force a retry.

### Step 3 — Verify the deployed edge and dashboard

```bash
# The saved L2 transaction already verified the image before creating ECS.
make demo-info

CLOUDFRONT=$(terraform -chdir=terraform/layers/l2-application/vantage-ai output -raw cloudfront_url)

curl "$CLOUDFRONT/health"
# → {"status":"ok","version":"1.0.0"}
```

### Step 4 — Configure Bedrock model access

1. AWS Console → Bedrock → Model access → Request access
2. Search "Claude Haiku 4.5" → check → Submit
3. Wait 2–5 minutes

Populate `bedrock_invoke_resource_arns` with the exact inference-profile ARN and
every destination foundation-model ARN reported by the actual profile. IAM must
allow both the profile and destinations; never guess destination regions.

### Step 5 — Verify end to end

```bash
BASE_URL=$(terraform -chdir=terraform/layers/l2-application/vantage-ai output -raw cloudfront_url)
API_KEY_SECRET=$(terraform -chdir=terraform/layers/l2-application/vantage-ai output -raw api_key_secret_name)
API_KEY=$(aws secretsmanager get-secret-value --secret-id "$API_KEY_SECRET" --query SecretString --output text)

# Upload
DOC_ID=$(curl -s -X POST "$BASE_URL/documents/upload" \
  -H "X-API-Key: $API_KEY" \
  -F "file=@sample-data.csv" | python3 -c "import sys,json; print(json.load(sys.stdin)['document_id'])")

# Wait for Lambda
sleep 5

# Status
curl -H "X-API-Key: $API_KEY" "$BASE_URL/documents/$DOC_ID/status"
# → "status": "completed"

# Records
curl -H "X-API-Key: $API_KEY" "$BASE_URL/records?document_id=$DOC_ID"

# AI Analysis
curl -X POST -H "X-API-Key: $API_KEY" \
  "$BASE_URL/insights/analyze?document_id=$DOC_ID"
curl -H "X-API-Key: $API_KEY" \
  "$BASE_URL/insights/anomalies?document_id=$DOC_ID"
```

## CI/CD

Pull requests and pushes to `main` or `feature/**` run credential-free quality gates for Python
(including the full Alembic history on PostgreSQL 16), the AWS-compatible Lambda
ZIP, backend-free Terraform validation, Trivy IaC checks, and a locally built
container image with Trivy vulnerability and misconfiguration scanning. CI never
assumes an AWS role, reads repository secrets, pushes an image, or deploys.

The Lambda and container artifacts are built from the checked-out Git commit.
The Lambda ZIP is passed to Terraform validation at the same path used by the L2
module, while the container is scanned locally and is never published. Major
GitHub-maintained actions use stable major tags; pin every remaining action to a
reviewed commit SHA before a final production release. Trivy is already SHA-pinned
because it executes third-party security tooling.

Automatic deployment remains intentionally disabled. A later manual portfolio
demo workflow must resolve deployment coordinates from `portfolio` Terraform
outputs and retain the repository's account, workspace, saved-plan, and source
provenance preflight.

## Destroy Everything

```bash
make tf-destroy
# Destroys L2 → L1 → L0, with Terraform confirmation for each layer.
```

Destroy is intentionally independent of Docker, ECR image availability, and the
current Git commit; it supplies a validation-only placeholder image tag while
Terraform destroys the deployed state.

The protected bootstrap bucket is not part of routine environment cleanup. See
[ADR 001](docs/adr/001-ephemeral-portfolio-environment.md) and
[ADR 002](docs/adr/002-terraform-state-and-layering.md),
[ADR 003](docs/adr/003-low-cost-network-and-edge.md), and
[ADR 004](docs/adr/004-managed-secrets-and-terraform-state.md) for lifecycle,
network, cost, and secret decisions. The configuration has been validated
without AWS credentials or a backend connection; a cold Terraform provider
cache still requires registry network access.
These instructions do not claim that a real AWS deployment has occurred.

## Project Structure

```
├── app/                     # FastAPI application
│   ├── main.py              # Entry point, routes registration
│   ├── Dockerfile           # Container build (python:3.12-slim)
│   ├── requirements.txt
│   ├── core/                # Validated settings, API-key auth, JSON logging
│   ├── models/record.py     # SQLAlchemy models (Document, Record)
│   ├── routers/
│   │   ├── documents.py     # Upload & status endpoints
│   │   ├── records.py       # Record listing & retrieval
│   │   └── insights.py      # AI analysis endpoints
│   └── services/
│       ├── bedrock_service.py  # Bounded Bedrock client + response contracts
│       ├── storage_service.py  # Local/S3 document storage adapters
│       └── sqs_service.py      # Versioned SQS job publisher
├── lambda/processor/        # Lambda function for async CSV processing
│   ├── handler.py           # SQS-triggered, parses CSV → RDS
│   └── package.zip          # Pre-built deployment package (x86_64)
├── terraform/
│   ├── bootstrap/           # Local-state S3 backend and GitHub OIDC bootstrap
│   ├── environments/portfolio/ # Safe examples; populated values stay ignored
│   └── layers/              # L0 foundation → L1 platform → L2 application
├── .github/workflows/       # CI/CD (GitHub Actions)
├── docker-compose.yml       # Local dev (API + PostgreSQL)
├── Makefile                 # All project commands
├── sample-data.csv          # 10-row test CSV (includes $75k anomaly)
└── vantage-ai-test-plan.md  # external test plan & acceptance criteria
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| ECS task won't start (CannotPullContainerError) | Rebuild with `--platform linux/amd64` |
| Bedrock AccessDeniedException (Legacy model) | Use Inference Profile: `au.anthropic.claude-haiku-4-5-20251001-v1:0` |
| Bedrock AccessDeniedException | Confirm the exact configured inference-profile ARN is enabled and matches IAM |
| Lambda not triggering | Check SQS → Lambda event source mapping exists |
| Lambda fails, DLQ has messages | RDS security group may not allow Lambda SG |
| Direct ALB request times out | Expected: ALB port 80 accepts only the CloudFront origin-facing prefix list |
| Lambda cannot reach AWS APIs | Confirm S3 gateway and Secrets Manager interface endpoints and endpoint SG |
