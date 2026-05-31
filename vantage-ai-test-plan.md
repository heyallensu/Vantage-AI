# Vantage AI — Test Plan & Success Criteria

How to verify your deployment is working. Run each check in order.
A section is done when every checkbox is ticked.

---

## WEEK 1 — Local Stack + AWS Infrastructure

### ✅ Local (Docker Compose)

```bash
make dev
# Expected: two containers start — api and db
# api:  listening on 0.0.0.0:8000
# db:   postgres ready on 5432
```

**Check 1 — Health endpoint**
```bash
curl http://localhost:8000/health
```
Expected:
```json
{"status": "ok", "version": "1.0.0"}
```

**Check 2 — Upload a document**
```bash
curl -X POST http://localhost:8000/documents/upload \
  -F "file=@sample-data.csv"
```
Expected:
```json
{
  "document_id": "a1b2c3d4-...",
  "status": "pending",
  "message": "Document accepted. Poll /documents/{id}/status for progress."
}
```
Save the `document_id` — you need it for all the checks below.

**Check 3 — Document status (local: should complete instantly)**
```bash
curl http://localhost:8000/documents/<document_id>/status
```
Expected:
```json
{"document_id": "...", "status": "completed", "error": null}
```

**Check 4 — Records were extracted**
```bash
curl "http://localhost:8000/records?document_id=<document_id>"
```
Expected: array of 10 records matching the CSV rows.

**Check 5 — AI analysis**
```bash
curl -X POST "http://localhost:8000/insights/analyze?document_id=<document_id>"
```
Expected:
```json
{
  "total_amount": 95393.5,
  "record_count": 10,
  "top_categories": ["Technology", "Professional Services", "Marketing"],
  "summary": "...",
  "anomalies": ["Unusually large transfer of $75,000 on 2024-01-30 categorised as Unknown"]
}
```

**Check 6 — Swagger UI**
Open http://localhost:8000/docs in browser.
Expected: all endpoints visible and testable.

**Local stack ✅ when:** all 6 checks pass.

---

### ✅ AWS — Terraform Infrastructure

```bash
make tf-plan-l0    # review L0 (VPC)
make tf-plan-l1    # review L1 (ECS/ECR/ALB)
make tf-plan-l2    # review L2 (SQS/RDS/Lambda/Service)
make tf-apply-l0   # (already applied)
make tf-apply-l1   # create ECS/ECR/ALB
make tf-apply-l2   # create SQS/RDS/Lambda/Service
```

After apply, Terraform outputs should include:
```
ecr_repository_url  = "123456.dkr.ecr.ap-southeast-2.amazonaws.com/vantage-ai-api"
ecs_cluster_name    = "vantage-ai-cluster"
rds_endpoint        = "vantage-ai.xxxx.ap-southeast-2.rds.amazonaws.com"
sqs_queue_url       = "https://sqs.ap-southeast-2.amazonaws.com/123456/vantage-ai-queue"
sqs_dlq_url         = "https://sqs.ap-southeast-2.amazonaws.com/123456/vantage-ai-dlq"
alb_dns_name        = "vantage-ai-alb-xxxx.ap-southeast-2.elb.amazonaws.com"
```

**Check 1 — ECS cluster exists**
```bash
aws ecs list-clusters --region ap-southeast-2
```
Expected: `vantage-ai-cluster` in the list.

**Check 2 — RDS is available**
```bash
aws rds describe-db-instances \
  --query "DBInstances[*].[DBInstanceIdentifier,DBInstanceStatus]" \
  --region ap-southeast-2
```
Expected: `vantage-ai` with status `available`.

**Check 3 — SQS queue exists**
```bash
aws sqs list-queues --region ap-southeast-2
```
Expected: both `vantage-ai-queue` and `vantage-ai-dlq` in the list.

**Check 4 — ECR repository exists**
```bash
aws ecr describe-repositories --region ap-southeast-2
```
Expected: `vantage-ai-api` in the list.

**Check 5 — Lambda function exists**
```bash
aws lambda list-functions --region ap-southeast-2 \
  --query "Functions[*].FunctionName"
```
Expected: `vantage-ai-processor` in the list.

**Infrastructure ✅ when:** all 5 checks pass and `terraform apply` exits with no errors.

---

### ✅ AWS — ECS Deployment

```bash
make build   # docker build
make push    # push to ECR
make deploy  # force new ECS deployment
```

**Check 1 — Task is RUNNING**
```bash
aws ecs list-tasks --cluster vantage-ai-cluster --region ap-southeast-2
```
Then describe the task and confirm `lastStatus: RUNNING`.

**Check 2 — ALB health check passes**
```bash
aws elbv2 describe-target-health \
  --target-group-arn <your-target-group-arn> \
  --region ap-southeast-2
```
Expected: `HealthStatus: healthy` for at least one target.

**Check 3 — Hit the ALB directly**
```bash
curl http://<alb_dns_name>/health
```
Expected:
```json
{"status": "ok", "version": "1.0.0"}
```

**ECS deployment ✅ when:** task is RUNNING, health check is healthy, ALB responds.

---

### ✅ SQS + Lambda Integration

**Check 1 — Upload via ALB triggers SQS**
```bash
curl -X POST http://<alb_dns_name>/documents/upload \
  -F "file=@sample-data.csv"
```
Expected: 202 response with `document_id`.

**Check 2 — Lambda processes the message**
```bash
# Check Lambda logs in CloudWatch
aws logs tail /aws/lambda/vantage-ai-processor --follow --region ap-southeast-2
```
Expected log lines like:
```
[OK] document_id=<uuid> → 10 records inserted
```

**Check 3 — Document status updated to completed**
```bash
curl http://<alb_dns_name>/documents/<document_id>/status
```
Expected: `"status": "completed"`.

**Check 4 — Records exist in database**
```bash
curl "http://<alb_dns_name>/records?document_id=<document_id>"
```
Expected: 10 records.

**Check 5 — DLQ is empty (nothing failed)**
```bash
aws sqs get-queue-attributes \
  --queue-url <sqs_dlq_url> \
  --attribute-names ApproximateNumberOfMessages \
  --region ap-southeast-2
```
Expected: `ApproximateNumberOfMessages: 0`.

**SQS + Lambda ✅ when:** all 5 checks pass. Lambda logs show success. DLQ is empty.

---

## WEEK 2 — AI Endpoints + CI/CD + DNS

### ✅ AI Endpoints

**Check 1 — /insights/analyze returns structured JSON**
```bash
curl -X POST "http://<alb_dns_name>/insights/analyze?document_id=<document_id>"
```
Expected: JSON with `total_amount`, `record_count`, `top_categories`, `summary`, `anomalies`.
The $75,000 "Unexpected Transfer" **must appear in anomalies** — this validates the AI prompt is working correctly.

**Check 2 — /insights/summary returns plain text**
```bash
curl "http://<alb_dns_name>/insights/summary?document_id=<document_id>"
```
Expected: JSON with a `summary` key containing 2-4 readable English sentences.

**Check 3 — /insights/anomalies returns a list**
```bash
curl "http://<alb_dns_name>/insights/anomalies?document_id=<document_id>"
```
Expected: JSON with an `anomalies` key containing at least one item (the $75,000 transfer).

**AI endpoints ✅ when:** all 3 checks pass and the anomaly detection correctly flags the $75,000 transfer.

---

### ✅ GitHub Actions CI/CD

Make a small change — edit the version in `/health` to `"1.0.1"`. Commit and push to `main`.

**Check 1 — Workflow triggers**
On GitHub → Actions tab → confirm a new workflow run starts within 30 seconds of the push.

**Check 2 — All steps pass**
Pipeline steps in order:
- `Lint and Test` → green
- `Build and Push to ECR` → green
- `Deploy to ECS` → green
- `Smoke Test` → green

**Check 3 — New version deployed**
```bash
curl http://<alb_dns_name>/health
```
Expected: `"version": "1.0.1"` — confirms the new image was deployed.

**Check 4 — Old tasks replaced (rolling deploy)**
```bash
aws ecs list-tasks --cluster vantage-ai-cluster --region ap-southeast-2
```
Describe the tasks — confirm they were started after your commit timestamp.

**CI/CD ✅ when:** pipeline is fully green and version bump is visible on the live endpoint.

---

### ✅ Route53 + Custom Domain

```bash
curl https://api.vantage-ai.com.au/health
```
Expected:
```json
{"status": "ok", "version": "1.0.1"}
```

Also check:
```bash
nslookup api.vantage-ai.com.au
```
Expected: resolves to an ALB IP address.

**Domain ✅ when:** HTTPS request to the custom domain returns a valid response.

---

## Final End-to-End Test

Run this sequence from scratch against the production domain.

```bash
BASE="https://api.vantage-ai.com.au"

# 1. Health
curl $BASE/health

# 2. Upload document
DOC=$(curl -s -X POST $BASE/documents/upload -F "file=@sample-data.csv")
echo $DOC
DOC_ID=$(echo $DOC | python3 -c "import sys,json; print(json.load(sys.stdin)['document_id'])")

# 3. Wait for processing (Lambda takes a few seconds)
sleep 10

# 4. Check status
curl $BASE/documents/$DOC_ID/status

# 5. List records
curl "$BASE/records?document_id=$DOC_ID" | python3 -m json.tool

# 6. AI analysis
curl -X POST "$BASE/insights/analyze?document_id=$DOC_ID" | python3 -m json.tool

# 7. Anomalies — $75k transfer must be flagged
curl "$BASE/insights/anomalies?document_id=$DOC_ID" | python3 -m json.tool
```

**Project is DONE when:**
- [ ] All local checks pass
- [ ] All AWS infrastructure is Terraform-managed (no manual Console clicking)
- [ ] Upload → SQS → Lambda → RDS pipeline works end-to-end
- [ ] All three AI endpoints return structured, meaningful responses
- [ ] The $75,000 anomaly is flagged by AI
- [ ] GitHub Actions workflow deploys automatically on push to main
- [ ] Custom domain resolves and returns HTTPS responses
- [ ] `make destroy` tears down all infrastructure cleanly
- [ ] README explains the architecture and how to run it

---

## Common Failure Modes & Fixes

| Symptom | Likely cause | Fix |
|---|---|---|
| ECS task keeps restarting | App not listening on `0.0.0.0:8000` | Change uvicorn `--host 0.0.0.0` |
| ECS task won't start | ECR pull fails (403) | Attach `AmazonECSTaskExecutionRolePolicy` to execution role |
| Lambda not triggering | SQS trigger not configured | Check Lambda → Triggers in Console |
| Lambda fails, message in DLQ | DB connection refused | Check RDS security group allows Lambda's SG |
| AI returns text not JSON | Claude added extra explanation | Add `Reply ONLY with valid JSON` to prompt |
| Route53 doesn't resolve | Missing alias record or wrong hosted zone | Check Route53 hosted zone matches domain registrar NS records |
| Pipeline fails on deploy step | GitHub Actions OIDC role not configured | Add `AWS_GITHUB_DEPLOY_ROLE_ARN` secret to GitHub repo → Settings → Secrets and variables → Actions |
