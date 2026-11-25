SHELL := /bin/sh

.DEFAULT_GOAL := help

.PHONY: help checkout up down logs status verify ui-install ui-dev ui-build ui-test

help: ## Show available commands.
	@awk 'BEGIN {FS = ":.*##"}; /^[a-zA-Z0-9_-]+:.*##/ {printf "%-12s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

checkout: ## Initialise/update the unmodified ERPNext source checkout.
	@./scripts/checkout-erpnext.sh

up: checkout ## Start the local, official ERPNext evaluation stack.
	@./scripts/start-erpnext.sh

down: ## Stop the local ERPNext stack and retain its Docker volumes.
	@./scripts/erpnext-compose.sh down

logs: ## Stream local ERPNext container logs.
	@./scripts/erpnext-compose.sh logs -f

status: ## Show local ERPNext container status.
	@./scripts/erpnext-compose.sh ps

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
