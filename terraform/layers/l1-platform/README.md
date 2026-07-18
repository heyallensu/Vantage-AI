# L1 Platform

This executable root composes the existing ECS cluster, ECR, shared ALB, and
monitoring modules. It reads the matching workspace's L0 outputs from the S3
remote state configured by `state_bucket`, `state_region`, and
`state_workspace_key_prefix`.

Its ECR repository and ECS cluster outputs are the sole source for Makefile push
and deployment coordinates. Apply L0 before planning this layer.
