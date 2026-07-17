# Vantage-AI

An Intelligent Document Processing Platform — upload CSV documents, extract records asynchronously, and get AI-powered insights via Amazon Bedrock.

## Architecture

```
Client → ALB → ECS Fargate (FastAPI)
                   │       │       │
                   │       │       └──→ Amazon Bedrock
                   │       └──→ S3 (encrypted source CSV)
                   └──→ SQS + DLQ ──→ Lambda ──→ RDS PostgreSQL
```

| Component | Technology |
|---|---|
| API | FastAPI (Python 3.12), Uvicorn |
| Database | PostgreSQL 16 (RDS) |
| Source Storage | Amazon S3 (private, encrypted objects with SHA-256 metadata) |
| Message Queue | Amazon SQS + DLQ |
| Async Processing | AWS Lambda (VPC-attached) |
| AI Analysis | Amazon Bedrock — Claude Haiku 4.5 (Inference Profile) |
| Container Runtime | ECS Fargate |
| Load Balancer | Application Load Balancer |
| Infra as Code | Terraform (3 layers: Foundation → Platform → Application) |
| CI/CD | GitHub Actions (OIDC) |

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

## Runtime Security and Configuration

All document, record, and insight endpoints require the `X-API-Key` header. The API uses a timing-safe comparison and never includes the key in its structured logs. `/health` and `/ready` stay public for load-balancer probes.

Non-local startup fails immediately unless these values are present:

- `API_KEY`
- `AWS_DEFAULT_REGION`
- `DATABASE_URL`
- `DOCUMENT_BUCKET`
- `SQS_QUEUE_URL`

Use [.env.example](.env.example) only as a local template. Production secrets belong in a managed secret store, not source control or Terraform variable files.

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

### Step 2 — Check and initialize the three layers

```bash
# Uses no AWS credentials or backend; a cold provider cache still downloads
# providers from the Terraform registry.
make tf-check

make tf-init
make tf-workspace

# Review all three plans in dependency order. This requires .aws-account-id.
export TF_VAR_db_password='<short-lived-database-password>'
make tf-plan

# Build Lambda package (Linux x86_64)
make lambda-package

# Apply only after reviewing the plans; each layer keeps Terraform confirmation.
make tf-apply
```

### Step 3 — Build and deploy the app

```bash
# ECR repository/registry and ECS cluster/service names come from Terraform outputs.
make push && make deploy

ALB=$(terraform -chdir=terraform/layers/l1-platform output -raw shared_alb_dns_name)

curl "http://$ALB/health"
# → {"status":"ok","version":"1.0.0"}
```

### Step 4 — Enable Bedrock model access

1. AWS Console → Bedrock → Model access → Request access
2. Search "Claude Haiku 4.5" → check → Submit
3. Wait 2–5 minutes

### Step 5 — Verify end to end

```bash
ALB="http://<your-alb-dns>"
API_KEY="<your-short-lived-api-key>"

# Upload
DOC_ID=$(curl -s -X POST "$ALB/documents/upload" \
  -H "X-API-Key: $API_KEY" \
  -F "file=@sample-data.csv" | python3 -c "import sys,json; print(json.load(sys.stdin)['document_id'])")

# Wait for Lambda
sleep 5

# Status
curl -H "X-API-Key: $API_KEY" "$ALB/documents/$DOC_ID/status"
# → "status": "completed"

# Records
curl -H "X-API-Key: $API_KEY" "$ALB/records?document_id=$DOC_ID"

# AI Analysis
curl -X POST -H "X-API-Key: $API_KEY" \
  "$ALB/insights/analyze?document_id=$DOC_ID"
curl -H "X-API-Key: $API_KEY" \
  "$ALB/insights/anomalies?document_id=$DOC_ID"
```

## CI/CD

Automatic deployment is intentionally disabled while the repository is being
separated from the former project environment. Pull-request quality gates and
the later manual portfolio demo workflow must not contain fixed AWS resource
names; they resolve deployment coordinates from the `portfolio` Terraform
outputs.

## Destroy Everything

```bash
make tf-destroy
# Destroys L2 → L1 → L0, with Terraform confirmation for each layer.
```

The protected bootstrap bucket is not part of routine environment cleanup. See
[ADR 001](docs/adr/001-ephemeral-portfolio-environment.md) and
[ADR 002](docs/adr/002-terraform-state-and-layering.md) for lifecycle and state
ownership decisions. This repository configuration has been validated offline;
these instructions do not claim that a real AWS deployment has occurred.

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
| Bedrock AccessDeniedException (Marketplace) | Ensure IAM role has `aws-marketplace:ViewSubscriptions` + `aws-marketplace:Subscribe` |
| Lambda not triggering | Check SQS → Lambda event source mapping exists |
| Lambda fails, DLQ has messages | RDS security group may not allow Lambda SG |
