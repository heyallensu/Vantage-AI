ENV ?= portfolio
override ENV := $(value ENV)
APP ?= vantage-ai
PYTHON ?= .venv/bin/python
DEPLOY_COMMIT ?= HEAD
override DEPLOY_COMMIT := $(value DEPLOY_COMMIT)
IMAGE_TAG ?=
override IMAGE_TAG := $(value IMAGE_TAG)
AWS_REGION ?= ap-southeast-2
override AWS_REGION := $(value AWS_REGION)
export DEPLOY_COMMIT IMAGE_TAG AWS_REGION

SUPPORTED_ENV := portfolio
ACCOUNT_FILE := .aws-account-id
BOOTSTRAP_DIR := terraform/bootstrap
ENV_DIR := terraform/environments/$(ENV)
L0_DIR := terraform/layers/l0-foundation
L1_DIR := terraform/layers/l1-platform
L2_DIR := terraform/layers/l2-application/vantage-ai
LAMBDA_DIR := lambda/processor
TF_PLUGIN_CACHE_DIR ?= /tmp/vantage-ai-terraform-plugin-cache
TF_PLAN_DIR := $(CURDIR)/.tfplans/$(ENV)

L0_TFVARS := $(ENV_DIR)/l0-foundation.tfvars
L1_TFVARS := $(ENV_DIR)/l1-platform.tfvars
L2_TFVARS := $(ENV_DIR)/l2-application-vantage-ai.tfvars
L0_BACKEND := $(ENV_DIR)/l0-foundation.backend.hcl
L1_BACKEND := $(ENV_DIR)/l1-platform.backend.hcl
L2_BACKEND := $(ENV_DIR)/l2-application-vantage-ai.backend.hcl

ACCOUNT_ENV = TF_VAR_allowed_account_id="$$(tr -d '[:space:]' < $(ACCOUNT_FILE))"

ifneq ($(ENV),$(SUPPORTED_ENV))
$(error Unsupported ENV '$(ENV)'; only '$(SUPPORTED_ENV)' is allowed)
endif

.PHONY: dev down logs db-migrate db-current lint test audit check lambda-package lambda-package-ci build ensure-image push deploy demo-info destroy validate-deployment-inputs \
	bootstrap tf-fmt tf-init tf-workspace tf-check tf-plan tf-apply tf-destroy tf-plan-l0 tf-apply-l0 \
	tf-plan-l1 tf-apply-l1 tf-plan-l2 tf-apply-l2 require-plan-dir \
	require-account verify-aws-context require-portfolio-workspaces \
	require-layer-config require-bootstrap-config require-source-provenance

dev:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f api db

db-migrate:
	DATABASE_URL=postgresql://vantage:vantage@localhost:5432/vantage $(PYTHON) -m scripts.database.migrate

db-current:
	DATABASE_URL=postgresql://vantage:vantage@localhost:5432/vantage $(PYTHON) -m alembic current

lint:
	$(PYTHON) -m ruff check app alembic lambda scripts tests

test:
	AWS_EC2_METADATA_DISABLED=true AWS_DEFAULT_REGION=ap-southeast-2 ENV=local $(PYTHON) -m pytest --cov=app --cov-report=term-missing --cov-fail-under=70

audit:
	$(PYTHON) -m pip_audit -r app/requirements.txt
	$(PYTHON) -m pip_audit -r lambda/processor/requirements.txt

check: lint test audit

lambda-package: require-source-provenance
	.venv/bin/python -m scripts.deploy.workflow package-lambda

# CI packages the checked-out commit without deployment account/workspace preflight.
lambda-package-ci:
	$(PYTHON) -m scripts.deploy.workflow package-lambda-ci

require-account:
	@test -s $(ACCOUNT_FILE) || { echo "Missing $(ACCOUNT_FILE); add the permitted 12-digit AWS account ID locally." >&2; exit 1; }
	@account_id="$$(tr -d '[:space:]' < $(ACCOUNT_FILE))"; echo "$$account_id" | grep -Eq '^[0-9]{12}$$' || { echo "$(ACCOUNT_FILE) must contain exactly one 12-digit AWS account ID." >&2; exit 1; }

verify-aws-context: require-account
	@expected="$$(tr -d '[:space:]' < $(ACCOUNT_FILE))"; actual="$$(aws sts get-caller-identity --query Account --output text)"; test "$$actual" = "$$expected" || { echo "AWS caller account does not match the locally approved account." >&2; exit 1; }

require-portfolio-workspaces:
	@for directory in $(L0_DIR) $(L1_DIR) $(L2_DIR); do workspace="$$(terraform -chdir="$$directory" workspace show)"; test "$$workspace" = "$(SUPPORTED_ENV)" || { echo "$$directory must use the $(SUPPORTED_ENV) workspace; found $$workspace." >&2; exit 1; }; done

require-layer-config:
	@for file in $(L0_TFVARS) $(L1_TFVARS) $(L2_TFVARS) $(L0_BACKEND) $(L1_BACKEND) $(L2_BACKEND); do test -s "$$file" || { echo "Missing or empty $$file; copy its .example file and replace placeholders." >&2; exit 1; }; if grep -Eq '<[^>]+>' "$$file"; then echo "Unresolved placeholder in $$file." >&2; exit 1; fi; terraform fmt -check "$$file" >/dev/null || { echo "Invalid or unformatted Terraform configuration: $$file." >&2; exit 1; }; done

require-bootstrap-config:
	@test -f $(BOOTSTRAP_DIR)/terraform.tfvars || { echo "Missing $(BOOTSTRAP_DIR)/terraform.tfvars; copy terraform.tfvars.example and replace placeholders." >&2; exit 1; }

require-source-provenance:
	@.venv/bin/python -m scripts.deploy.workflow validate-inputs

validate-deployment-inputs:
	@.venv/bin/python -m scripts.deploy.workflow validate-inputs

require-plan-dir:
	@mkdir -p $(TF_PLAN_DIR)

# One-time local-state bootstrap. Terraform prompts before making AWS changes.
bootstrap: verify-aws-context require-bootstrap-config
	$(ACCOUNT_ENV) terraform -chdir=$(BOOTSTRAP_DIR) init -input=false
	$(ACCOUNT_ENV) terraform -chdir=$(BOOTSTRAP_DIR) apply -input=false -var-file=terraform.tfvars

tf-fmt:
	terraform fmt -recursive $(BOOTSTRAP_DIR)
	terraform fmt -recursive terraform/layers

# Offline syntax/module check: no backend and no AWS credentials are required.
tf-check:
	terraform fmt -recursive -check $(BOOTSTRAP_DIR)
	terraform fmt -recursive -check terraform/layers
	@mkdir -p $(TF_PLUGIN_CACHE_DIR)
	@data_dir="$$(mktemp -d /tmp/vantage-ai-tf-check-bootstrap.XXXXXX)"; trap 'rm -rf "$$data_dir"' EXIT; AWS_EC2_METADATA_DISABLED=true TF_PLUGIN_CACHE_DIR=$(TF_PLUGIN_CACHE_DIR) TF_DATA_DIR="$$data_dir" terraform -chdir=$(BOOTSTRAP_DIR) init -backend=false -input=false; AWS_EC2_METADATA_DISABLED=true TF_PLUGIN_CACHE_DIR=$(TF_PLUGIN_CACHE_DIR) TF_DATA_DIR="$$data_dir" terraform -chdir=$(BOOTSTRAP_DIR) validate
	@data_dir="$$(mktemp -d /tmp/vantage-ai-tf-check-l0.XXXXXX)"; trap 'rm -rf "$$data_dir"' EXIT; AWS_EC2_METADATA_DISABLED=true TF_DATA_DIR="$$data_dir" terraform -chdir=$(L0_DIR) init -backend=false -input=false -plugin-dir=$(TF_PLUGIN_CACHE_DIR); AWS_EC2_METADATA_DISABLED=true TF_DATA_DIR="$$data_dir" terraform -chdir=$(L0_DIR) validate
	@data_dir="$$(mktemp -d /tmp/vantage-ai-tf-check-l1.XXXXXX)"; trap 'rm -rf "$$data_dir"' EXIT; AWS_EC2_METADATA_DISABLED=true TF_DATA_DIR="$$data_dir" terraform -chdir=$(L1_DIR) init -backend=false -input=false -plugin-dir=$(TF_PLUGIN_CACHE_DIR); AWS_EC2_METADATA_DISABLED=true TF_DATA_DIR="$$data_dir" terraform -chdir=$(L1_DIR) validate
	@data_dir="$$(mktemp -d /tmp/vantage-ai-tf-check-l2.XXXXXX)"; trap 'rm -rf "$$data_dir"' EXIT; AWS_EC2_METADATA_DISABLED=true TF_DATA_DIR="$$data_dir" terraform -chdir=$(L2_DIR) init -backend=false -input=false -plugin-dir=$(TF_PLUGIN_CACHE_DIR); AWS_EC2_METADATA_DISABLED=true TF_DATA_DIR="$$data_dir" terraform -chdir=$(L2_DIR) validate

tf-init: verify-aws-context require-layer-config
	$(ACCOUNT_ENV) terraform -chdir=$(L0_DIR) init -input=false -backend-config=../../environments/$(ENV)/l0-foundation.backend.hcl
	$(ACCOUNT_ENV) terraform -chdir=$(L1_DIR) init -input=false -backend-config=../../environments/$(ENV)/l1-platform.backend.hcl
	$(ACCOUNT_ENV) terraform -chdir=$(L2_DIR) init -input=false -backend-config=../../../environments/$(ENV)/l2-application-vantage-ai.backend.hcl

tf-workspace: tf-init
	$(ACCOUNT_ENV) terraform -chdir=$(L0_DIR) workspace select $(ENV) || $(ACCOUNT_ENV) terraform -chdir=$(L0_DIR) workspace new $(ENV)
	$(ACCOUNT_ENV) terraform -chdir=$(L1_DIR) workspace select $(ENV) || $(ACCOUNT_ENV) terraform -chdir=$(L1_DIR) workspace new $(ENV)
	$(ACCOUNT_ENV) terraform -chdir=$(L2_DIR) workspace select $(ENV) || $(ACCOUNT_ENV) terraform -chdir=$(L2_DIR) workspace new $(ENV)

tf-plan:
	@echo "Monolithic tf-plan is disabled. Use tf-plan-l0/apply-l0, then L1, then L2." >&2
	@exit 2

tf-apply:
	@echo "Monolithic tf-apply is disabled. Apply only the reviewed saved layer plans." >&2
	@exit 2

tf-plan-l0: require-plan-dir
	.venv/bin/python -m scripts.deploy.workflow plan-l0

tf-apply-l0:
	.venv/bin/python -m scripts.deploy.workflow apply-l0

tf-plan-l1: require-plan-dir
	.venv/bin/python -m scripts.deploy.workflow plan-l1

tf-apply-l1:
	.venv/bin/python -m scripts.deploy.workflow apply-l1

tf-plan-l2: require-plan-dir
	.venv/bin/python -m scripts.deploy.workflow plan-l2

tf-apply-l2:
	.venv/bin/python -m scripts.deploy.workflow apply-l2

tf-destroy:
	.venv/bin/python -m scripts.deploy.workflow destroy

destroy: tf-destroy

# Build only committed files from DEPLOY_COMMIT; .dockerignore remains a second boundary.
build: require-source-provenance
	.venv/bin/python -m scripts.deploy.workflow build-image

ensure-image:
	.venv/bin/python -m scripts.deploy.workflow ensure-image

push: ensure-image

deploy:
	@echo "Standalone deploy is disabled. Apply the reviewed saved L2 plan with tf-apply-l2." >&2
	@exit 2

demo-info: require-portfolio-workspaces
	@echo "CloudFront URL: $$(terraform -chdir=$(L2_DIR) output -raw cloudfront_url)"
	@echo "API key secret: $$(terraform -chdir=$(L2_DIR) output -raw api_key_secret_name)"
	@echo "Document bucket: $$(terraform -chdir=$(L2_DIR) output -raw document_bucket_name)"
	@echo "Operations dashboard: $$(terraform -chdir=$(L2_DIR) output -raw operations_dashboard_url)"
	@echo "Cleanup identifiers:"
	@terraform -chdir=$(L2_DIR) output -json cleanup_identifiers
