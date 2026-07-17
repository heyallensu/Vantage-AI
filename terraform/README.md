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

Use the root Makefile as the supported interface. `make tf-check` is deliberately
offline with `init -backend=false`; all backend-connected or mutating commands
require the ignored `.aws-account-id` guard. See
`terraform/environments/portfolio/README.md` for configuration steps.

Bootstrap remains local-state by design because a state bucket cannot safely
own the state that creates itself. Preserve its ignored state securely. Do not
run `make bootstrap` in an account that already has the GitHub OIDC provider
unless the existing provider is first reviewed and imported.
