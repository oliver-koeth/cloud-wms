SHELL := /bin/sh

.DEFAULT_GOAL := help

.PHONY: help checkout image up down logs status verify install-app migrate demo-data app-test app-test-clean ui-install ui-dev ui-build ui-test

help: ## Show available commands.
	@awk 'BEGIN {FS = ":.*##"}; /^[a-zA-Z0-9_-]+:.*##/ {printf "%-12s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

checkout: ## Initialise/update the unmodified ERPNext source checkout.
	@./scripts/checkout-erpnext.sh

image: ## Build the ERPNext image with the cloud_wms app layered on top.
	@docker build -q -f docker/Containerfile -t cloud-wms/erpnext:v16.60.0-wms .

up: checkout image ## Start the local ERPNext stack with the cloud_wms app available.
	@./scripts/start-erpnext.sh

down: ## Stop the local ERPNext stack and retain its Docker volumes.
	@./scripts/erpnext-compose.sh down

logs: ## Stream local ERPNext container logs.
	@./scripts/erpnext-compose.sh logs -f

status: ## Show local ERPNext container status.
	@./scripts/erpnext-compose.sh ps

install-app: ## Install cloud_wms on the running site (first time only; `make migrate` afterwards).
	@./scripts/erpnext-compose.sh exec backend bench --site frontend install-app cloud_wms

migrate: ## Apply cloud_wms schema, roles, permissions and settings to the running site.
	@./scripts/erpnext-compose.sh exec backend bench --site frontend migrate

demo-data: ## Create demo users (Sales/Supervisor/Worker), locations and stock. Local sites only.
	@./scripts/erpnext-compose.sh exec backend bench --site frontend execute cloud_wms.setup.demo.setup_all

app-test: image ## Run cloud_wms tests on an isolated stack (first run takes several minutes).
	@./scripts/app-test.sh

app-test-clean: ## Remove the isolated test stack and its volumes.
	@./scripts/app-test.sh clean

verify: ## Validate the project scaffolding without starting containers.
	@./scripts/verify.sh

ui-install: ## Install the standalone WMS UI dependencies.
	@npm --prefix ui install

ui-dev: ## Start the WMS UI development server on http://localhost:5173.
	@npm --prefix ui run dev

ui-build: ## Type-check and build the WMS UI.
	@npm --prefix ui run build

ui-test: ## Run the WMS UI unit tests.
	@npm --prefix ui test
