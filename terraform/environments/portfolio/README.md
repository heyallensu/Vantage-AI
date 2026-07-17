# Portfolio Environment

`portfolio` is the only supported environment. It is intentionally ephemeral:
plan, apply, verify, and destroy it within the same short validation window.

## Local configuration

For each of the three layers, copy both examples and remove only the `.example`
suffix. The resulting `*.tfvars` and `*.backend.hcl` files are ignored by Git.
Use the bootstrap `state_bucket_name` output for every bucket placeholder, and
keep the backend `key` and `workspace_key_prefix` exactly aligned with the
remote-state variables.

Create `.aws-account-id` in the repository root with exactly the permitted
12-digit account ID. The Makefile validates it and exports it as
`TF_VAR_allowed_account_id`; account IDs are never committed to examples.

RDS generates and rotates its master password in Secrets Manager. No database
password or database URL belongs in a tfvars file or shell environment. Complete
the `owner`, `expires_at`, state coordinates, current Git SHA image tag, and
Bedrock resource list before planning. Obtain the exact inference-profile ARN
and all destination foundation-model ARNs from the actual profile; do not infer
destination regions. Unresolved placeholders fail the Makefile preflight.

Use the saved-plan sequence `tf-plan-l0/apply-l0`, then L1, then
`tf-plan-l2/apply-l2`. L2 planning ensures the immutable Git-SHA image and builds
Lambda from the same commit before saving the plan and checksum. Every apply
checks its plan SHA-256 manifest before Terraform runs. The ignored local
deployment provenance is the single-deployer trust root for the verified ECR
digest, and ECS uses the digest reference rather than the tag. If provenance is
lost after a tag exists, start a new commit transaction or use a separately
reviewed controlled recovery; image labels alone cannot restore trust. Cleanup
is `make tf-destroy`; it uses a fixed validation-only image tag and digest and
does not require Docker, ECR image availability, or the current deployment
commit.

## GitHub Environment configuration

Create a GitHub Environment named `portfolio`, then configure these Environment
variables. A required-reviewer rule also pauses the scheduled cleanup workflow,
so use one only when that operational tradeoff is intentional.

| Variable | Value |
|---|---|
| `AWS_ACCOUNT_ID` | The approved 12-digit account ID |
| `AWS_REGION` | `ap-southeast-2` unless intentionally changed |
| `AWS_DEPLOY_ROLE_ARN` | `github_deploy_role_arn` from bootstrap |
| `TF_STATE_BUCKET` | `state_bucket_name` from bootstrap |
| `PORTFOLIO_OWNER` | Short owner tag such as the GitHub username |
| `BEDROCK_MODEL_ID` | The exact cross-region inference profile ID |
| `BEDROCK_INFERENCE_PROFILE_ARN` | The account-owned inference profile ARN |
| `BEDROCK_FOUNDATION_MODEL_ARNS` | Comma-separated destination foundation-model ARNs |

`PORTFOLIO_EXPIRES_AT` is optional; the workflow uses the next UTC day when it
is empty. These values are identifiers and configuration, not long-lived AWS
credentials. The API key and RDS password are generated in Secrets Manager.

Run **Portfolio demo** manually with the exact confirmation `deploy portfolio`.
Its cleanup job assumes the OIDC role independently and runs even when deploy or
E2E verification fails. **Portfolio emergency destroy** requires the exact
confirmation `destroy portfolio`; its daily schedule also reconciles only the
dedicated `portfolio` state and then asserts that tagged runtime resources are
gone.
