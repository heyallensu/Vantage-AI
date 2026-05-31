ENV ?= dev
APP ?= vantage-ai

L0_DIR := terraform/$(ENV)/l0-foundation
L1_DIR := terraform/$(ENV)/l1-platform
L2_DIR := terraform/$(ENV)/l2-application/$(APP)

LAMBDA_DIR := lambda/processor

.PHONY: dev down logs lambda-package build push deploy destroy tf-fmt tf-init tf-workspace tf-validate tf-plan-l0 tf-plan-l1 tf-plan-l2 tf-apply-l0 tf-apply-l1 tf-apply-l2 tf-destroy-l0 tf-destroy-l1 tf-destroy-l2

dev:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f api db

lambda-package:
	docker run --rm --platform linux/amd64 -v "$$(pwd)/$(LAMBDA_DIR):/var/task" public.ecr.aws/sam/build-python3.12:latest /bin/sh -c "rm -rf package package.zip && pip install -r requirements.txt -t package && cp handler.py package/ && cd package && zip -r ../package.zip ."

# Build the API Docker image locally (same image GitHub Actions pushes to ECR).
ECR_REGISTRY ?= 314146318322.dkr.ecr.ap-southeast-2.amazonaws.com
ECR_REPO     ?= vantage-ai-dev-api
IMAGE_TAG    ?= latest

build:
	docker build --platform linux/amd64 -f app/Dockerfile -t $(ECR_REPO):$(IMAGE_TAG) .

# Push the local image to ECR.
push: build
	aws ecr get-login-password --region ap-southeast-2 | \
		docker login --username AWS --password-stdin $(ECR_REGISTRY)
	docker tag $(ECR_REPO):$(IMAGE_TAG) $(ECR_REGISTRY)/$(ECR_REPO):$(IMAGE_TAG)
	docker push $(ECR_REGISTRY)/$(ECR_REPO):$(IMAGE_TAG)

# Force a new ECS deployment (picks up the latest image tag).
deploy:
	aws ecs update-service \
		--region ap-southeast-2 \
		--cluster vantage-ai-dev-cluster \
		--service vantage-ai-dev-api \
		--force-new-deployment

# Destroy all infrastructure WITH CONFIRMATION (reverse order: L2 → L1 → L0).
destroy:
	@echo "⚠️  This will destroy ALL AWS resources for the dev environment!"
	@echo "Press Ctrl-C within 10 seconds to cancel..."
	@sleep 10
	$(MAKE) tf-destroy-l2
	$(MAKE) tf-destroy-l1
	$(MAKE) tf-destroy-l0

# Format Terraform files across all dev layers.
tf-fmt:
	terraform -chdir=$(L0_DIR) fmt -recursive
	terraform -chdir=$(L1_DIR) fmt -recursive
	terraform -chdir=$(L2_DIR) fmt -recursive

# Initialize Terraform providers and modules for all layers.
tf-init:
	terraform -chdir=$(L0_DIR) init
	terraform -chdir=$(L1_DIR) init
	terraform -chdir=$(L2_DIR) init

# Select or create the workspace for all layers.
tf-workspace:
	terraform -chdir=$(L0_DIR) workspace select $(ENV) || terraform -chdir=$(L0_DIR) workspace new $(ENV)
	terraform -chdir=$(L1_DIR) workspace select $(ENV) || terraform -chdir=$(L1_DIR) workspace new $(ENV)
	terraform -chdir=$(L2_DIR) workspace select $(ENV) || terraform -chdir=$(L2_DIR) workspace new $(ENV)

# Validate all Terraform layers.
tf-validate:
	terraform -chdir=$(L0_DIR) validate
	terraform -chdir=$(L1_DIR) validate
	terraform -chdir=$(L2_DIR) validate

tf-plan-l0:
	terraform -chdir=$(L0_DIR) plan

tf-plan-l1:
	terraform -chdir=$(L1_DIR) plan

tf-plan-l2:
	terraform -chdir=$(L2_DIR) plan

tf-apply-l0:
	terraform -chdir=$(L0_DIR) apply

tf-apply-l1:
	terraform -chdir=$(L1_DIR) apply

tf-apply-l2:
	terraform -chdir=$(L2_DIR) apply

tf-destroy-l0:
	terraform -chdir=$(L0_DIR) destroy

tf-destroy-l1:
	terraform -chdir=$(L1_DIR) destroy

tf-destroy-l2:
	terraform -chdir=$(L2_DIR) destroy
