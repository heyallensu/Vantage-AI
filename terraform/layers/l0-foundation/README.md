# L0 Foundation

This executable root composes the existing VPC and security-baseline child
modules. Its S3 backend is supplied at init time; the workspace controls the
environment suffix used in resource names.

The root exports VPC, subnet, CIDR, default security group, and optional NAT
Gateway identifiers for upper layers. Use `make tf-check` for credential-free
validation and the root Makefile for all backend-connected operations.
