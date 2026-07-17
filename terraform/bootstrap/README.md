# Terraform Bootstrap

This one-time root module deliberately keeps local state while it creates the
private, encrypted, versioned S3 bucket used by the three executable layers. It
also creates the GitHub Actions OIDC provider and a deployment role whose trust
policy accepts tokens from exactly one GitHub repository.

Copy `terraform.tfvars.example` to the ignored `terraform.tfvars`, replace every
placeholder, verify the active AWS credentials independently, and run
`make bootstrap`. The target prompts before applying; it never uses `-auto-approve`.

Keep `terraform/bootstrap/bootstrap.tfstate` secure and backed up. It contains
the ownership record for resources that cannot safely manage their own backend.
The state bucket has `prevent_destroy`; retirement therefore requires an
explicit reviewed change before the bucket can be removed.
