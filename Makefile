ENV ?= portfolio
APP ?= vantage-ai
PYTHON ?= .venv/bin/python
AWS_REGION ?= ap-southeast-2
IMAGE_TAG ?= latest

SUPPORTED_ENV := portfolio
ACCOUNT_FILE := .aws-account-id
BOOTSTRAP_DIR := terraform/bootstrap
ENV_DIR := terraform/environments/$(ENV)
L0_DIR := terraform/layers/l0-foundation
L1_DIR := terraform/layers/l1-platform
L2_DIR := terraform/layers/l2-application/vantage-ai
LAMBDA_DIR := lambda/processor
TF_PLUGIN_CACHE_DIR ?= /tmp/vantage-ai-terraform-plugin-cache

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

.PHONY: dev down logs db-migrate db-current lint test audit check lambda-package build push deploy destroy \
	bootstrap tf-fmt tf-init tf-workspace tf-check tf-plan tf-apply tf-destroy \
	require-account verify-aws-context require-portfolio-workspaces \
	require-layer-config require-bootstrap-config

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
	AWS_EC2_METADATA_DISABLED=true AWS_DEFAULT_REGION=$(AWS_REGION) ENV=local $(PYTHON) -m pytest --cov=app --cov-report=term-missing --cov-fail-under=70

audit:
	$(PYTHON) -m pip_audit -r app/requirements.txt
	$(PYTHON) -m pip_audit -r lambda/processor/requirements.txt

check: lint test audit

lambda-package:
	docker run --rm --platform linux/amd64 -v "$$(pwd)/$(LAMBDA_DIR):/var/task" public.ecr.aws/sam/build-python3.12:latest /bin/sh -c "rm -rf package package.zip && pip install -r requirements.txt -t package && cp handler.py package/ && cd package && zip -r ../package.zip ."

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

tf-plan: tf-workspace
	$(ACCOUNT_ENV) terraform -chdir=$(L0_DIR) plan -input=false -var-file=../../environments/$(ENV)/l0-foundation.tfvars
	$(ACCOUNT_ENV) terraform -chdir=$(L1_DIR) plan -input=false -var-file=../../environments/$(ENV)/l1-platform.tfvars
	$(ACCOUNT_ENV) terraform -chdir=$(L2_DIR) plan -input=false -var-file=../../../environments/$(ENV)/l2-application-vantage-ai.tfvars

tf-apply: tf-workspace
	$(ACCOUNT_ENV) terraform -chdir=$(L0_DIR) apply -input=false -var-file=../../environments/$(ENV)/l0-foundation.tfvars
	$(ACCOUNT_ENV) terraform -chdir=$(L1_DIR) apply -input=false -var-file=../../environments/$(ENV)/l1-platform.tfvars
	$(ACCOUNT_ENV) terraform -chdir=$(L2_DIR) apply -input=false -var-file=../../../environments/$(ENV)/l2-application-vantage-ai.tfvars

tf-destroy: tf-workspace
	$(ACCOUNT_ENV) terraform -chdir=$(L2_DIR) destroy -input=false -var-file=../../../environments/$(ENV)/l2-application-vantage-ai.tfvars
	$(ACCOUNT_ENV) terraform -chdir=$(L1_DIR) destroy -input=false -var-file=../../environments/$(ENV)/l1-platform.tfvars
	$(ACCOUNT_ENV) terraform -chdir=$(L0_DIR) destroy -input=false -var-file=../../environments/$(ENV)/l0-foundation.tfvars

destroy: tf-destroy

# Build locally; ECR coordinates are intentionally resolved only by `push`.
build:
	docker build --platform linux/amd64 -f app/Dockerfile -t $(APP):$(IMAGE_TAG) .

push: verify-aws-context require-portfolio-workspaces build
	@ecr_repository_url="$$( $(ACCOUNT_ENV) terraform -chdir=$(L1_DIR) output -raw ecr_repository_url )"; ecr_registry="$${ecr_repository_url%/*}"; aws ecr get-login-password --region $(AWS_REGION) | docker login --username AWS --password-stdin "$$ecr_registry"; docker tag $(APP):$(IMAGE_TAG) "$$ecr_repository_url:$(IMAGE_TAG)"; docker push "$$ecr_repository_url:$(IMAGE_TAG)"

deploy: verify-aws-context require-portfolio-workspaces
	@ecs_cluster="$$( $(ACCOUNT_ENV) terraform -chdir=$(L1_DIR) output -raw ecs_cluster_name )"; ecs_service="$$( $(ACCOUNT_ENV) terraform -chdir=$(L2_DIR) output -raw ecs_service_name )"; aws ecs update-service --region $(AWS_REGION) --cluster "$$ecs_cluster" --service "$$ecs_service" --force-new-deployment
