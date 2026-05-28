# Dev L1 Platform

This Terraform stack manages the **dev environment L1 shared platform layer** for the Vantage AI project.

## Purpose

L1 is the shared platform layer. It contains infrastructure that can be reused by one or more application workloads in the same environment.

This layer sits above L0 foundation and below L2 application workloads.

```text
L0 Foundation  -> network, security baseline, account foundation
L1 Platform    -> shared runtime and delivery platform
L2 Application -> app-specific workload resources
```

## Current Resources

This stack currently creates:

- ECS Cluster
- ECR Repository for API container images
- ECR lifecycle policy
- Shared Application Load Balancer
- Shared ALB security group
- HTTP listener with default fixed 404 response
- Shared CloudWatch ECS platform log group

## Directory Design

The project separates Terraform by **environment first**, then by **infrastructure layer**.

```text
terraform/
└── dev/
    └── l1-platform/
        ├── main.tf
        ├── variables.tf
        ├── outputs.tf
        ├── terraform.tfvars.example
        ├── README.md
        └── modules/
            ├── ecs-cluster/
            ├── ecr/
            ├── shared-alb/
            └── monitoring/
```

`terraform/dev/l1-platform` is a **root module**. This is where Terraform commands are executed.

The folders under `terraform/dev/l1-platform/modules/` are **child modules**. They are called by the root module and should not be applied directly.

## Dependency On L0

This stack depends on outputs from the dev L0 foundation stack.

The shared ALB needs:

- `vpc_id`
- `public_subnet_ids`

These values are read through Terraform remote state.

The L0 stack must be applied before planning or applying this L1 stack.

## What Belongs In L1

L1 includes shared platform resources such as:

- ECS Cluster
- EKS Cluster
- Shared ALB
- Shared ECR
- Shared CloudWatch / monitoring
- CI/CD deployment role
- Shared VPC endpoints if platform-managed

## What Does Not Belong In L1

Application-specific resources should not be placed in this layer.

Examples:

- ECS service for one application
- Lambda function for one application
- SQS queue used by only one application workflow
- RDS database used by only one application
- Application-specific IAM execution role
- Application-specific CloudWatch alarms
- Application-specific Route53 record
- Application secrets

Those resources belong in L2.

## Current Modules

### ECS Cluster Module

Creates a shared ECS Cluster for dev workloads.

L2 application stacks can later deploy ECS services into this cluster.

### ECR Module

Creates an ECR repository for API container images.

The repository enables image scanning on push and uses a lifecycle policy to keep the repository from growing without limit.

### Shared ALB Module

Creates a shared public Application Load Balancer.

The ALB has an HTTP listener with a default `404` fixed response. L2 applications will later add target groups and listener rules.

### Monitoring Module

Creates a shared CloudWatch log group for platform workloads.

L2 applications can use this log group from ECS task definitions, or create their own app-specific log groups if needed.

## How To Use

Initialize Terraform:

```bash
# Initialize Terraform providers and local modules.
terraform -chdir=terraform/dev/l1-platform init
```

Select or create the dev workspace:

```bash
# Select the dev workspace, or create it if it does not exist.
terraform -chdir=terraform/dev/l1-platform workspace select dev || terraform -chdir=terraform/dev/l1-platform workspace new dev
```

Format Terraform files:

```bash
# Format the L1 root module and child modules.
terraform -chdir=terraform/dev/l1-platform fmt -recursive
```

Validate Terraform:

```bash
# Validate Terraform syntax and module references.
terraform -chdir=terraform/dev/l1-platform validate
```

Preview the infrastructure plan:

```bash
# Review what Terraform would create before applying.
terraform -chdir=terraform/dev/l1-platform plan
```

## Outputs For L2 Application Layer

L2 application stacks will consume this stack's outputs through Terraform remote state.

Important outputs include:

- `ecs_cluster_id`
- `ecs_cluster_name`
- `ecs_cluster_arn`
- `ecr_repository_name`
- `ecr_repository_url`
- `ecr_repository_arn`
- `shared_alb_arn`
- `shared_alb_dns_name`
- `shared_alb_zone_id`
- `shared_alb_security_group_id`
- `shared_http_listener_arn`
- `ecs_platform_log_group_name`
- `ecs_platform_log_group_arn`
