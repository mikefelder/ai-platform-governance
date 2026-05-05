# Governance Hub — CLI Deploy Targets
# All deployments go through Azure CLI.

# --- Configuration (set via env or command line) ---
SUBSCRIPTION     ?= $(error Set SUBSCRIPTION – e.g. export SUBSCRIPTION=<your-sub-id>)
RESOURCE_GROUP   ?= $(error Set RESOURCE_GROUP – e.g. export RESOURCE_GROUP=<your-rg>)
ACR_NAME         ?= $(error Set ACR_NAME – e.g. export ACR_NAME=<your-acr>)
IMAGE_NAME       ?= uc3-governance-api
# IMAGE_TAG defaults to v<VERSION> (e.g. v0.2.0). Override via env/CLI to pin or test.
VERSION          := $(shell cat VERSION 2>/dev/null | tr -d '[:space:]')
IMAGE_TAG        ?= v$(VERSION)
GIT_SHA          := $(shell git rev-parse --short=7 HEAD 2>/dev/null)
CONTAINER_APP    ?= ca-uc3-governance

ACR_LOGIN_SERVER  = $(ACR_NAME).azurecr.io
FULL_IMAGE        = $(ACR_LOGIN_SERVER)/$(IMAGE_NAME):$(IMAGE_TAG)

# Service directory
SVC_DIR           = services/governance-api

.PHONY: help login acr-login build push acr-build deploy test lint clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# --- Authentication ---

login: ## Log in to Azure CLI
	az login
	az account set --subscription $(SUBSCRIPTION)

acr-login: ## Log in to the ACR (requires public access or VPN)
	az acr login --name $(ACR_NAME) --subscription $(SUBSCRIPTION)

# --- Build & Push ---

# Stage gateway policy sources into the build context so the running
# container can compute /api/policies/gateway/digest (TC-2f). Without
# this step the digest endpoint reports "unknown" because the Dockerfile
# WORKDIR cannot reach ../../infra at runtime.
stage-policy-sources:
	@mkdir -p $(SVC_DIR)/policy_sources
	@cp infra/main.apim.tf $(SVC_DIR)/policy_sources/main.apim.tf 2>/dev/null || true
	@echo "Staged $$(ls $(SVC_DIR)/policy_sources/ 2>/dev/null | wc -l | tr -d ' ') policy source(s) for digest"

build: stage-policy-sources ## Build the Docker image locally
	docker build -t $(FULL_IMAGE) -f $(SVC_DIR)/Dockerfile $(SVC_DIR)

push: acr-login build ## Build and push Docker image to ACR
	docker push $(FULL_IMAGE)

acr-build: stage-policy-sources ## Build image remotely using ACR Tasks. Tags both v<VERSION> and sha-<git>.
	az acr build \
		--registry $(ACR_NAME) \
		--subscription $(SUBSCRIPTION) \
		--image $(IMAGE_NAME):$(IMAGE_TAG) \
		$(if $(GIT_SHA),--image $(IMAGE_NAME):sha-$(GIT_SHA),) \
		--file $(SVC_DIR)/Dockerfile \
		$(SVC_DIR)

# --- Deploy ---

deploy: ## Update the Container App to use the latest image
	az containerapp update \
		--name $(CONTAINER_APP) \
		--resource-group $(RESOURCE_GROUP) \
		--subscription $(SUBSCRIPTION) \
		--image $(FULL_IMAGE)

deploy-full: push deploy ## Build, push, and deploy in one step

# --- Enable/disable ACR public access (for push from outside VNet) ---

acr-enable-public: ## Temporarily enable ACR public network access
	az acr update \
		--name $(ACR_NAME) \
		--subscription $(SUBSCRIPTION) \
		--public-network-enabled true

acr-disable-public: ## Re-disable ACR public network access
	az acr update \
		--name $(ACR_NAME) \
		--subscription $(SUBSCRIPTION) \
		--public-network-enabled false

# --- Development ---

test: ## Run pytest for the governance-api
	cd $(SVC_DIR) && pip install -e ".[dev]" && pytest -v

lint: ## Run ruff linter
	cd $(SVC_DIR) && pip install ruff && ruff check src/ tests/

run-local: ## Run the API locally (dev mode)
	cd $(SVC_DIR) && uvicorn governance_api.main:app --reload --port 8000

# --- Infrastructure ---

tf-init: ## Initialize Terraform
	cd infra && terraform init

tf-plan: ## Plan Terraform changes
	cd infra && terraform plan

tf-apply: ## Apply Terraform changes
	cd infra && terraform apply

tf-destroy: ## Destroy Terraform resources
	cd infra && terraform destroy

# --- Cleanup ---

clean: ## Remove build artifacts
	rm -rf $(SVC_DIR)/build $(SVC_DIR)/dist $(SVC_DIR)/src/*.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
