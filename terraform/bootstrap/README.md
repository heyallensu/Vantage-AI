# Terraform Bootstrap

This one-time root module deliberately keeps local state while it creates the
private, encrypted, versioned S3 bucket used by the three executable layers. It
also creates the GitHub Actions OIDC provider and a deployment role whose trust
policy accepts tokens only from the repository's `portfolio` GitHub Environment.
The role has a two-hour maximum session for the bounded demo transaction and
service-specific managed policies for the Terraform resources in L0, L1, and L2.

Copy `terraform.tfvars.example` to the ignored `terraform.tfvars`, replace every
placeholder, verify the active AWS credentials independently, and run
`make bootstrap`. The target prompts before applying; it never uses `-auto-approve`.
The GitHub owner and repository IDs must match the immutable IDs embedded by the
repository's customized OIDC subject template. Retrieve them with
`gh api users/<owner> --jq .id` and
`gh api repos/<owner>/<repository> --jq .id`.

Keep `terraform/bootstrap/bootstrap.tfstate` secure and backed up. It contains
the ownership record for resources that cannot safely manage their own backend.
The state bucket has `prevent_destroy`; retirement therefore requires an
explicit reviewed change before the bucket can be removed.

After bootstrap, copy these outputs into GitHub Environment variables:

| Bootstrap output | GitHub Environment variable |
|---|---|
| `state_bucket_name` | `TF_STATE_BUCKET` |
| `github_deploy_role_arn` | `AWS_DEPLOY_ROLE_ARN` |

Create the GitHub Environment with the exact name `portfolio` before running
`make bootstrap`, because the role trust subject is bound to that environment.
The application workflows never require long-lived AWS access keys.
