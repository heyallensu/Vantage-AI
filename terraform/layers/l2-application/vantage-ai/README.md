# L2 Application: Vantage AI

This executable root composes private S3 storage, SQS/DLQ, managed-secret RDS,
least-privilege IAM, Lambda, one public-subnet ECS task, VPC endpoints,
CloudFront/OAC, and alarms. It consumes the matching workspace's L0 and L1 S3
remote state.

The root Makefile builds `lambda/processor/package.zip` before L2 planning and
passes the locally trusted ECR digest. The task definition uses an immutable
`repository@sha256:...` reference; the Git SHA tag is retained only as
provenance. ECR, cluster, load-balancer, dashboard, VPC, subnet, and route-table
inputs are consumed only from Terraform outputs. No database password input
exists. Destroy this layer before L1 and L0; versioned application buckets use
`force_destroy`.
