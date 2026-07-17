# L2 Application: Vantage AI

This executable root preserves the application composition: SQS/DLQ, RDS,
application IAM, Lambda, ECS service, and alarms. It consumes the matching
workspace's L0 and L1 S3 remote state.

Before planning, build `lambda/processor/package.zip`, provide
`TF_VAR_db_password` through a secure environment, and apply L0 then L1. ECR,
cluster, and load-balancer inputs are consumed only from Terraform outputs.
Destroy this layer before L1 and L0.
