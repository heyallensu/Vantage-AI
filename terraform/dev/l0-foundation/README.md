# Dev L0 Foundation

This Terraform stack manages the **dev environment L0 AWS foundation** for the Vantage AI project.

## Purpose

L0 is the stable foundation layer of the AWS environment. It contains resources that are shared by upper layers and should change less frequently than application workloads.

This stack currently creates:

- VPC
- Public subnets
- Private subnets
- Internet Gateway
- Public route table
- Private route table
- Optional NAT Gateway
- Locked default security group

## Directory Design

This project separates Terraform by **environment first**, then by **infrastructure layer**.

```text
terraform/
└── dev/
    └── l0-foundation/
        ├── main.tf
        ├── variables.tf
        ├── outputs.tf
        ├── terraform.tfvars.example
        ├── README.md
        └── modules/
            ├── vpc/
            └── security-baseline/
```

`terraform/dev/l0-foundation` is a **root module**. This is where Terraform commands are executed.

The folders under `terraform/dev/l0-foundation/modules/` are **child modules**. They are called by the root module and should not be applied directly.

## What Belongs In L0

L0 includes foundation resources such as:

- VPC
- Subnets
- Route tables
- Internet Gateway
- NAT Gateway
- Security baseline
- OIDC provider
- Base IAM roles
- KMS baseline
- Route53 hosted zone

## What Does Not Belong In L0

Application-specific resources should not be placed in this layer.

Examples:

- ECS service
- Lambda function
- SQS document queue
- RDS database for one application
- App-specific IAM execution role
- App-specific CloudWatch alarms
- App-specific Route53 record
- Application secrets

Those resources belong in L1 or L2.

## Current Modules

### VPC Module

The VPC module creates the base network:

- VPC
- Public subnets
- Private subnets
- Internet Gateway
- Public route table
- Private route table
- Optional NAT Gateway

### Security Baseline Module

The security baseline module locks down the default security group so the VPC does not rely on implicit default access.

Application-specific security groups will be created later in L2.

## How To Use

Initialize Terraform:

```bash
# Initialize Terraform providers and local modules.
terraform -chdir=terraform/dev/l0-foundation init
```

Select or create the dev workspace:

```bash
# Select the dev workspace, or create it if it does not exist.
terraform -chdir=terraform/dev/l0-foundation workspace select dev || terraform -chdir=terraform/dev/l0-foundation workspace new dev
```

Format Terraform files:

```bash
# Format the L0 root module and child modules.
terraform -chdir=terraform/dev/l0-foundation fmt -recursive
```

Validate Terraform:

```bash
# Validate Terraform syntax and module references.
terraform -chdir=terraform/dev/l0-foundation validate
```

Preview the infrastructure plan:

```bash
# Review what Terraform would create before applying.
terraform -chdir=terraform/dev/l0-foundation plan
```

## Outputs For Upper Layers

L1 and L2 stacks will consume this stack's outputs later through Terraform remote state.

Important outputs include:

- `environment`
- `vpc_id`
- `public_subnet_ids`
- `private_subnet_ids`
- `default_security_group_id`
- `nat_gateway_id`

## Cost Note

The dev environment keeps NAT Gateway disabled by default to avoid NAT Gateway hourly cost.

Production can enable NAT Gateway or use VPC endpoints depending on the final architecture.
