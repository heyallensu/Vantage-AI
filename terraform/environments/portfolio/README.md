# Portfolio Environment

`portfolio` is the only supported environment. It is intentionally ephemeral:
plan, apply, verify, and destroy it within the same short validation window.

## Local configuration

For each of the three layers, copy both examples and remove only the `.example`
suffix. The resulting `*.tfvars` and `*.backend.hcl` files are ignored by Git.
Use the bootstrap `state_bucket_name` output for every bucket placeholder, and
keep the backend `key` and `workspace_key_prefix` exactly aligned with the
remote-state variables.

Create `.aws-account-id` in the repository root with exactly the permitted
12-digit account ID. The Makefile validates it and exports it as
`TF_VAR_allowed_account_id`; account IDs are never committed to examples.

The database password remains an environment-only secret:

```bash
export TF_VAR_db_password='<short-lived-secret>'
```

Then use `make tf-init`, `make tf-workspace`, `make tf-plan`, and only after a
manual plan review, `make tf-apply`. Cleanup is `make tf-destroy` and proceeds
in reverse dependency order.
