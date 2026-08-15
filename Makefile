DOCKER_COMPOSE := docker compose
PYTHON         := python
API_DIR        := apps/api
WEB_DIR        := apps/web

.PHONY: install web-install dev test test-all lint format format-check typecheck \
	package wheel-check wheel-import forbidden evidence web-test web-lint web-build \
	web-e2e check-api check-web check docker-up docker-down demo worker migrate \
	migrate-create seed reset clean help

install: ## Install the self-contained API with development checks
	$(PYTHON) -m pip install -e "$(API_DIR)[dev]"

dev: ## Run the API locally (uvicorn on :8000)
	cd $(API_DIR) && uvicorn app.main:app --reload --port 8000

test: ## Run API unit tests (no live infra needed)
	$(PYTHON) -m pytest $(API_DIR)/tests -q --ignore=$(API_DIR)/tests/integration --basetemp=.pytest-temp-make-unit

test-all: ## Run every offline API contract, including integration-shaped tests
	cd $(API_DIR) && $(PYTHON) -m pytest tests -q

lint: ## Lint the API with ruff
	$(PYTHON) -m ruff check $(API_DIR)/app $(API_DIR)/tests examples scripts

format: ## Format the API with ruff
	$(PYTHON) -m ruff format $(API_DIR)/app $(API_DIR)/tests examples scripts

format-check: ## Check API formatting without changing files
	$(PYTHON) -m ruff format --check $(API_DIR)/app $(API_DIR)/tests examples scripts

typecheck: ## Type-check the API with pyright
	$(PYTHON) -m pyright $(API_DIR)/app

package: ## Build the API wheel from repository-local sources
	$(PYTHON) -m build $(API_DIR)

wheel-check: package ## Verify the wheel includes the internal vendor package
	$(PYTHON) scripts/check_wheel_contents.py

wheel-import: wheel-check ## Install the wheel in a clean environment and import it
	$(PYTHON) scripts/verify_isolated_wheel.py

forbidden: ## Fail if an actionable external shared-core dependency returns
	$(PYTHON) scripts/check_forbidden_dependencies.py

evidence: ## Generate and verify deterministic offline portfolio evidence/checksums
	$(PYTHON) scripts/portfolio_demo.py
	$(PYTHON) scripts/verify_portfolio_evidence.py

web-install: ## Install the locked frontend dependency graph
	cd $(WEB_DIR) && npm ci

web-test: ## Run frontend Vitest tests
	cd $(WEB_DIR) && npm test

web-lint: ## Run frontend ESLint
	cd $(WEB_DIR) && npm run lint

web-build: ## Build the production frontend bundle
	cd $(WEB_DIR) && npm run build

web-e2e: ## Run desktop and mobile Chromium Playwright tests
	cd $(WEB_DIR) && npm run test:e2e:chromium

check-api: test lint format-check typecheck forbidden wheel-import evidence ## Run all offline API gates

check-web: web-test web-lint web-build web-e2e ## Run all frontend gates (dependencies/browser must be installed)

check: check-api check-web ## Run the complete local quality gate

docker-up: ## Start Postgres + Redis + API + web
	$(DOCKER_COMPOSE) up -d

docker-down: ## Stop all containers
	$(DOCKER_COMPOSE) down

demo: ## Run the offline grounded-RAG + refusal demo
	$(PYTHON) examples/run_demo.py

worker: ## Start the Celery worker
	cd $(API_DIR) && celery -A app.core.celery.celery_app worker --loglevel=info

migrate: ## Apply Alembic migrations
	cd $(API_DIR) && alembic upgrade head

migrate-create: ## Create a new Alembic migration (msg=...)
	cd $(API_DIR) && alembic revision --autogenerate -m "$(msg)"

seed: ## Seed sample data via the running API
	$(PYTHON) scripts/seed.py --api-url http://localhost:8000 --data-dir ./data/sample

reset: ## Reset the database (drop + recreate + seed)
	$(PYTHON) scripts/reset_db.py --confirm --seed

clean: ## Remove caches
	$(PYTHON) -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').rglob('__pycache__')]; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').rglob('.pytest_cache')]; shutil.rmtree('.ruff_cache', ignore_errors=True)"

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'
