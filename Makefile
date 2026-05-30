ENV ?= dev
APP ?= vantage-ai

L0_DIR := terraform/$(ENV)/l0-foundation
L1_DIR := terraform/$(ENV)/l1-platform
L2_DIR := terraform/$(ENV)/l2-application/$(APP)

LAMBDA_DIR := lambda/processor

.PHONY: dev down logs lambda-package tf-fmt tf-init tf-workspace tf-validate tf-plan-l0 tf-plan-l1 tf-plan-l2 tf-apply-l0 tf-apply-l1 tf-apply-l2

dev:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f api db

lambda-package:
	docker run --rm -v "$$(pwd)/$(LAMBDA_DIR):/var/task" public.ecr.aws/lambda/python:3.12:latest /bin/sh -c "rm -rf package package.zip && pip install -r requirements.txt -t package && cd handler.py package/ && cd package && zip -r ../package.zip ."

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