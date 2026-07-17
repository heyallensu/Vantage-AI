# Terraform Layout

Vantage AI uses one bootstrap root and three executable infrastructure layers:

```text
terraform/
├── bootstrap/                         # local state; S3 backend + GitHub OIDC
├── environments/portfolio/            # ignored runtime config + safe examples
└── layers/
    ├── l0-foundation/                 # VPC and security baseline
    ├── l1-platform/                   # ECS cluster, ECR, ALB, monitoring
    └── l2-application/vantage-ai/      # application workload
```

The dependency direction is L0 → L1 → L2. L1 reads L0 state from S3; L2 reads
both L0 and L1 state. Every backend uses the same bucket and
`workspace_key_prefix`, while each layer has a distinct key. The active
`portfolio` workspace therefore keeps the three state objects separate.

Use the root Makefile as the supported interface. `make tf-check` uses no AWS
credentials or backend (`init -backend=false`), although a cold provider cache
requires Terraform Registry network access. All backend-connected or mutating
commands require the ignored `.aws-account-id` guard. See
`terraform/environments/portfolio/README.md` for configuration steps.

Infrastructure changes use saved plans under the ignored
`.tfplans/portfolio/` directory. The supported transaction is:

1. `make tf-plan-l0` → inspect → `make tf-apply-l0`.
2. `make tf-plan-l1` → inspect → `make tf-apply-l1`.
3. `make tf-plan-l2` ensures the immutable commit image, packages Lambda from
   that same commit, saves its checksum, and writes the L2 plan.
4. Inspect the L2 plan, then run `make tf-apply-l2`; apply first verifies the
   plan's SHA-256 manifest, then verifies commit, tag, ECR digest, and Lambda
   checksum before accepting the saved plan.

The ignored `deployment-provenance.json` in that directory is the
single-deployer trust root. Existing ECR tags are reusable only when local
metadata, the ECR digest, the pulled `RepoDigest`, and the full-SHA revision
label all agree. L2 pins the ECS task to `repository@sha256:...`. Losing the
metadata does not authorize reconstructing it from an image label: use a new
commit transaction or an explicit independently reviewed recovery.

The old monolithic `tf-plan`, `tf-apply`, and standalone `deploy` targets fail
with guidance instead of silently planning or applying multiple layers.

Bootstrap remains local-state by design because a state bucket cannot safely
own the state that creates itself. Preserve its ignored state securely. Do not
run `make bootstrap` in an account that already has the GitHub OIDC provider
unless the existing provider is first reviewed and imported.
