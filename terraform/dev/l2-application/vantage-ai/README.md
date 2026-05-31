# Dev L2 Application - Vantage AI

This Terraform stack manages the **dev environment L2 application layer** for the Vantage AI intelligent document processing platform.

## Purpose

L2 is the application workload layer. It contains resources that belong specifically to one application.

For this project, the L2 application is **Vantage AI**.

This layer sits above:

```text
L0 Foundation  -> network, routing, security baseline
L1 Platform    -> shared ECS cluster, ECR, shared ALB, monitoring
L2 Application -> Vantage AI app-specific resources
```

## Current Resources

This stack currently creates:

- SQS document processing queue
- SQS dead letter queue
- RDS PostgreSQL database
- RDS subnet group
- RDS security group
- ECS execution role
- ECS task role
- Lambda execution role
- Lambda processor function
- Lambda security group
- Lambda log group
- SQS event source mapping for Lambda
- ECS task definition
- ECS Fargate service
- App-specific ECS security group
- ALB target group
- ALB listener rule
- CloudWatch alarm for DLQ messages
- CloudWatch alarm for Lambda errors

## Directory Design

The project separates Terraform by **environment first**, then by **infrastructure layer**.

```text
terraform/
└── dev/
    └── l2-application/
        └── vantage-ai/
            ├── main.tf
            ├── variables.tf
            ├── outputs.tf
            ├── terraform.tfvars.example
            ├── README.md
            └── modules/
                ├── iam/
                ├── ecs-service/
                ├── sqs/
                ├── rds/
                ├── lambda/
                └── alarms/
```

`terraform/dev/l2-application/vantage-ai` is a **root module**. This is where Terraform commands are executed.

The folders under `terraform/dev/l2-application/vantage-ai/modules/` are **child modules**. They are called by the root module and should not be applied directly.

## Dependencies On L0 And L1

This stack consumes outputs from both lower layers through Terraform remote state.

### L0 Outputs Used

From `terraform/dev/l0-foundation`:

- `vpc_id`
- `public_subnet_ids`
- `private_subnet_ids`

These values are used for:

- RDS private subnet placement
- Lambda VPC configuration
- ECS service network configuration
- Security group creation

### L1 Outputs Used

From `terraform/dev/l1-platform`:

- `ecs_cluster_id`
- `ecr_repository_url`
- `shared_alb_security_group_id`
- `shared_http_listener_arn`
- `ecs_platform_log_group_name`

These values are used for:

- ECS service deployment
- ECS task image location
- ALB routing
- ECS log configuration

## Application Data Flow

The Vantage AI platform follows this flow:

```text
Client
  -> Shared ALB
  -> ECS Fargate FastAPI service
  -> SQS document processing queue
  -> Lambda processor
  -> RDS PostgreSQL
  -> FastAPI records and insights endpoints
```

## Module Responsibilities

### SQS Module

Creates:

- Main document processing queue
- Dead letter queue
- Redrive policy

The FastAPI upload endpoint sends document processing jobs to this queue.

### RDS Module

Creates:

- PostgreSQL database
- DB subnet group
- Database security group

The Lambda processor writes parsed records to this database. The FastAPI service reads records from it.

### IAM Module

Creates:

- ECS execution role
- ECS task role
- Lambda execution role

The ECS task role allows the FastAPI app to send messages to SQS and invoke Bedrock models.

The Lambda execution role allows the processor to consume messages from SQS, write CloudWatch logs, and run inside the VPC.

### Lambda Module

Creates:

- Lambda function
- Lambda security group
- Lambda CloudWatch log group
- SQS event source mapping

The Lambda function receives SQS messages, parses uploaded CSV data, writes records to RDS, and updates document status.

### ECS Service Module

Creates:

- ECS task definition
- ECS Fargate service
- App-specific security group
- ALB target group
- ALB listener rule

This module deploys the FastAPI application behind the shared ALB.

### Alarms Module

Creates:

- DLQ visible messages alarm
- Lambda errors alarm

These alarms help detect failed document processing.

## Secrets And Sensitive Values

Do not commit sensitive values.

The database password should be passed through an environment variable when running Terraform:

```bash
export TF_VAR_db_password="replace-with-a-strong-password"
```

Do not put this value in:

- `terraform.tfvars.example`
- Git
- README files
- shell history in real production use

For a production system, use AWS Secrets Manager or SSM Parameter Store.

## Lambda Package

The Lambda function expects a zip package at:

```text
lambda/processor/package.zip
```

Build it from the repository root:

```bash
make lambda-package
```

## How To Use

Initialize Terraform:

```bash
terraform -chdir=terraform/dev/l2-application/vantage-ai init
```

Select or create the dev workspace:

```bash
terraform -chdir=terraform/dev/l2-application/vantage-ai workspace select dev || terraform -chdir=terraform/dev/l2-application/vantage-ai workspace new dev
```

Format Terraform files:

```bash
terraform -chdir=terraform/dev/l2-application/vantage-ai fmt -recursive
```

Validate Terraform:

```bash
terraform -chdir=terraform/dev/l2-application/vantage-ai validate
```

Preview the infrastructure plan:

```bash
export TF_VAR_db_password="replace-with-a-strong-password"
terraform -chdir=terraform/dev/l2-application/vantage-ai plan
```

Apply only after reviewing the plan:

```bash
export TF_VAR_db_password="replace-with-a-strong-password"
terraform -chdir=terraform/dev/l2-application/vantage-ai apply
```

## Outputs

Important outputs include:

- `sqs_queue_url`
- `sqs_queue_arn`
- `sqs_dlq_url`
- `db_endpoint`
- `database_security_group_id`
- `ecs_execution_role_arn`
- `ecs_task_role_arn`
- `lambda_execution_role_arn`
- `lambda_function_name`
- `ecs_service_name`
- `ecs_task_definition_arn`
- `app_target_group_arn`
- `dlq_alarm_name`
- `lambda_errors_alarm_name`

## Cost Notes

This stack may create billable resources, including:

- RDS PostgreSQL instance
- Lambda invocations
- CloudWatch logs
- ECS Fargate tasks
- ALB target group usage
- SQS requests

Review `terraform plan` carefully before applying.
