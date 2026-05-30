# Dev Terraform Environment

This directory contains the Terraform stacks for the **dev environment** of the Vantage AI project.

The project separates infrastructure by **environment first**, then by **infrastructure layer**.

```text
terraform/
└── dev/
    ├── l0-foundation/
    ├── l1-platform/
    └── l2-application/
        └── vantage-ai/
```

## Layer Overview

### L0 Foundation

Path:

```text
terraform/dev/l0-foundation
```

L0 owns stable AWS foundation resources.

Examples:

- VPC
- Public subnets
- Private subnets
- Route tables
- Internet Gateway
- Optional NAT Gateway
- Security baseline

L0 should change less frequently than application code.

### L1 Platform

Path:

```text
terraform/dev/l1-platform
```

L1 owns shared platform resources that can be reused by application workloads.

Examples:

- ECS Cluster
- ECR Repository
- Shared Application Load Balancer
- Shared ALB listener
- Shared CloudWatch log group

L1 reads outputs from L0 through Terraform remote state.

### L2 Application

Path:

```text
terraform/dev/l2-application/vantage-ai
```

L2 owns resources that belong specifically to the Vantage AI application.

Examples:

- SQS document processing queue
- SQS dead letter queue
- RDS PostgreSQL database
- Lambda processor
- ECS Fargate service
- App-specific IAM roles
- App-specific security groups
- App-specific CloudWatch alarms

L2 reads outputs from both L0 and L1 through Terraform remote state.

## Dependency Direction

The dependency direction is one-way:

```text
L0 Foundation
  ↓
L1 Platform
  ↓
L2 Application
```

This means:

- L0 does not depend on L1 or L2.
- L1 depends on L0.
- L2 depends on L0 and L1.

## Why This Structure

This structure reduces blast radius and clarifies ownership.

- Foundation changes can be reviewed separately from application changes.
- Shared platform changes can be applied without rewriting app-specific resources.
- Application resources can evolve faster without constantly changing the network foundation.

## Terraform Workspace

Each layer uses the `dev` Terraform workspace.

Example:

```bash
terraform -chdir=terraform/dev/l0-foundation workspace select dev || terraform -chdir=terraform/dev/l0-foundation workspace new dev
```

The workspace keeps state organized for the dev environment and satisfies the project requirement that Terraform workspaces are enabled.

## Apply Order

Apply the layers in this order.

### 1. L0 Foundation

```bash
terraform -chdir=terraform/dev/l0-foundation init
terraform -chdir=terraform/dev/l0-foundation workspace select dev || terraform -chdir=terraform/dev/l0-foundation workspace new dev
terraform -chdir=terraform/dev/l0-foundation fmt -recursive
terraform -chdir=terraform/dev/l0-foundation validate
terraform -chdir=terraform/dev/l0-foundation plan
terraform -chdir=terraform/dev/l0-foundation apply
```

### 2. L1 Platform

Run this only after L0 has been applied.

```bash
terraform -chdir=terraform/dev/l1-platform init
terraform -chdir=terraform/dev/l1-platform workspace select dev || terraform -chdir=terraform/dev/l1-platform workspace new dev
terraform -chdir=terraform/dev/l1-platform fmt -recursive
terraform -chdir=terraform/dev/l1-platform validate
terraform -chdir=terraform/dev/l1-platform plan
terraform -chdir=terraform/dev/l1-platform apply
```

### 3. L2 Application - Vantage AI

Run this only after L0 and L1 have been applied.

The L2 stack requires a database password.

```bash
export TF_VAR_db_password="replace-with-a-strong-password"
```

Then run:

```bash
terraform -chdir=terraform/dev/l2-application/vantage-ai init
terraform -chdir=terraform/dev/l2-application/vantage-ai workspace select dev || terraform -chdir=terraform/dev/l2-application/vantage-ai workspace new dev
terraform -chdir=terraform/dev/l2-application/vantage-ai fmt -recursive
terraform -chdir=terraform/dev/l2-application/vantage-ai validate
terraform -chdir=terraform/dev/l2-application/vantage-ai plan
terraform -chdir=terraform/dev/l2-application/vantage-ai apply
```

## Remote State Usage

L1 reads outputs from L0.

L2 reads outputs from both L0 and L1.

With local backend and the `dev` workspace, the state paths are:

```text
terraform/dev/l0-foundation/terraform.tfstate.d/dev/terraform.tfstate
terraform/dev/l1-platform/terraform.tfstate.d/dev/terraform.tfstate
```

In a production team environment, this would usually be replaced with an S3 backend and DynamoDB state locking.

## Sensitive Values

Do not commit secrets to Git.

Do not commit:

- Database passwords
- API keys
- AWS credentials
- Bedrock secrets
- GitHub tokens

For dev, pass sensitive Terraform variables through environment variables:

```bash
export TF_VAR_db_password="replace-with-a-strong-password"
```

For production, use AWS Secrets Manager, SSM Parameter Store, or a secure CI/CD secret store.

## Cost Notes

Some resources in this environment may create AWS charges.

Potentially billable resources include:

- NAT Gateway if enabled
- Application Load Balancer
- ECS Fargate tasks
- RDS PostgreSQL instance
- CloudWatch logs
- Lambda invocations
- SQS requests

Always review `terraform plan` before running `terraform apply`.

## Troubleshooting

### Remote state not found

If L1 cannot read L0 state, apply L0 first.

If L2 cannot read L0 or L1 state, apply both lower layers first.

### Missing Lambda package

The L2 Lambda module expects:

```text
lambda/processor/package.zip
```

Build it before planning or applying L2.

### Missing database password

Set:

```bash
export TF_VAR_db_password="replace-with-a-strong-password"
```

before planning or applying L2.

## Review Explanation

This dev environment is split into L0, L1, and L2 Terraform stacks.

L0 creates the stable AWS foundation. L1 reads L0 outputs and creates the shared platform. L2 reads both L0 and L1 outputs and creates the Vantage AI application resources.

This design keeps the network foundation, shared platform, and application workload separate, while still allowing the layers to pass outputs through Terraform remote state.