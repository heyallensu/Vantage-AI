# Vantage-AI

An Intelligent Document Processing Platform — upload CSV documents, extract records asynchronously, and get AI-powered insights via Amazon Bedrock.

## Architecture

```
Client → ALB (HTTP :80) → ECS Fargate (FastAPI :8000)
                              │
                              ▼
                           SQS Queue ──→ Lambda (processor)
                              │              │
                              ▼              ▼
                    Amazon Bedrock      RDS PostgreSQL
                    (Claude Haiku 4.5)
```

| Component | Technology |
|---|---|
| API | FastAPI (Python 3.12), Uvicorn |
| Database | PostgreSQL 16 (RDS) |
| Message Queue | Amazon SQS + DLQ |
| Async Processing | AWS Lambda (VPC-attached) |
| AI Analysis | Amazon Bedrock — Claude Haiku 4.5 (Inference Profile) |
| Container Runtime | ECS Fargate |
| Load Balancer | Application Load Balancer |
| Infra as Code | Terraform (3 layers: Foundation → Platform → Application) |
| CI/CD | GitHub Actions (OIDC) |

## Data Flow

1. **Upload** — Client POSTs a CSV to `/documents/upload`
2. **Queue** — API stores raw CSV in RDS and sends `document_id` to SQS
3. **Process** — Lambda picks up the SQS message, parses CSV rows, inserts `Record` rows
4. **Query** — Client polls `/documents/{id}/status` then fetches `/records`
5. **Analyze** — Client calls `/insights/analyze` — API sends records to Bedrock for AI summary + anomaly detection

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `POST` | `/documents/upload` | Upload CSV (multipart form) |
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

# 2. Health check
curl http://localhost:8000/health

# 3. Upload sample CSV
curl -X POST http://localhost:8000/documents/upload \
  -F "file=@sample-data.csv"

# 4. Check status (document processes instantly in local mode)
curl http://localhost:8000/documents/<DOC_ID>/status

# 5. View records
curl "http://localhost:8000/records?document_id=<DOC_ID>"

# 6. Stop
make down
```

> **Note:** Local mode (`ENV=local`) processes CSV inline without SQS/Lambda. Bedrock calls still require valid AWS credentials.

## Deployment — AWS

### Prerequisites

- AWS CLI configured with admin credentials
- Terraform ≥ 1.6.0
- Docker (with BuildKit for `linux/amd64` cross-build)
- GitHub repo with `AWS_GITHUB_DEPLOY_ROLE_ARN` secret (for CI/CD OIDC)

### Step 1 — Infrastructure

```bash
# Copy and edit tfvars
cp terraform/dev/l0-foundation/terraform.tfvars.example terraform/dev/l0-foundation/terraform.tfvars
cp terraform/dev/l1-platform/terraform.tfvars.example    terraform/dev/l1-platform/terraform.tfvars
cp terraform/dev/l2-application/vantage-ai/terraform.tfvars.example \
   terraform/dev/l2-application/vantage-ai/terraform.tfvars
# Edit L2 tfvars → set db_password

# Initialize all layers
make tf-init
make tf-workspace

# Deploy layer by layer
make tf-apply-l0   # VPC, subnets (~2 min)
make tf-apply-l1   # ECS cluster, ECR, ALB (~5 min)

# Build Lambda package (Linux x86_64)
make lambda-package

make tf-apply-l2   # SQS, RDS, Lambda, ECS service (~10 min)
```

### Step 2 — Build & Deploy the App

```bash
# Build Docker image (linux/amd64), push to ECR, deploy
make push && make deploy

# Wait ~60s for Fargate task to start, then verify
ALB=$(terraform -chdir=terraform/dev/l2-application/vantage-ai output -raw shared_alb_dns_name 2>/dev/null \
  || aws elbv2 describe-load-balancers --names vantage-ai-dev-shared-alb \
       --region ap-southeast-2 --query 'LoadBalancers[0].DNSName' --output text)

curl "http://$ALB/health"
# → {"status":"ok","version":"1.0.0"}
```

### Step 3 — Enable Bedrock Model Access

1. AWS Console → Bedrock → Model access → Request access
2. Search "Claude Haiku 4.5" → check → Submit
3. Wait 2–5 minutes

### Step 4 — Verify End-to-End

```bash
ALB="http://<your-alb-dns>"

# Upload
DOC_ID=$(curl -s -X POST "$ALB/documents/upload" \
  -F "file=@sample-data.csv" | python3 -c "import sys,json; print(json.load(sys.stdin)['document_id'])")

# Wait for Lambda
sleep 5

# Status
curl "$ALB/documents/$DOC_ID/status"
# → "status": "completed"

# Records
curl "$ALB/records?document_id=$DOC_ID"

# AI Analysis
curl -X POST "$ALB/insights/analyze?document_id=$DOC_ID"
curl "$ALB/insights/anomalies?document_id=$DOC_ID"
```

## CI/CD

Push to `main` triggers the GitHub Actions workflow (`.github/workflows/deploy.yml`):

```
Lint and Test → Build & Push to ECR → Deploy to ECS → Smoke Test
```

Required GitHub secret:
- `AWS_GITHUB_DEPLOY_ROLE_ARN` — IAM role ARN for OIDC-based AWS auth

## Destroy Everything

```bash
make destroy
# ⚠️  Destroys L2 → L1 → L0. Irreversible.
```

Or destroy individual layers:
```bash
make tf-destroy-l2
make tf-destroy-l1
make tf-destroy-l0
```

## Project Structure

```
├── app/                     # FastAPI application
│   ├── main.py              # Entry point, routes registration
│   ├── Dockerfile           # Container build (python:3.12-slim)
│   ├── requirements.txt
│   ├── models/record.py     # SQLAlchemy models (Document, Record)
│   ├── routers/
│   │   ├── documents.py     # Upload & status endpoints
│   │   ├── records.py       # Record listing & retrieval
│   │   └── insights.py      # AI analysis endpoints
│   └── services/
│       ├── bedrock_service.py  # Bedrock Claude Haiku 4.5 client
│       └── sqs_service.py      # SQS message producer
├── lambda/processor/        # Lambda function for async CSV processing
│   ├── handler.py           # SQS-triggered, parses CSV → RDS
│   └── package.zip          # Pre-built deployment package (x86_64)
├── terraform/dev/           # Infrastructure as Code (3 layers)
│   ├── l0-foundation/       # VPC, subnets, IGW, security baseline
│   ├── l1-platform/         # ECS cluster, ECR, ALB, monitoring
│   └── l2-application/      # SQS, RDS, Lambda, IAM, ECS service, alarms
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

---


