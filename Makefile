DOCKER_COMPOSE := docker compose
PYTHON         := python
API_DIR        := apps/api
WEB_DIR        := apps/web

.PHONY: install dev test test-all lint format typecheck docker-up docker-down demo \
        worker migrate migrate-create seed reset clean help

install: ## Install shared-core and API dependencies
	pip install -e ../shared-core
	pip install -r $(API_DIR)/requirements.txt
	pip install pytest pytest-asyncio pytest-cov respx ruff

dev: ## Run the API locally (uvicorn on :8000)
	cd $(API_DIR) && uvicorn app.main:app --reload --port 8000

test: ## Run API unit tests (no live infra needed)
	cd $(API_DIR) && $(PYTHON) -m pytest tests -q --ignore=tests/integration

test-all: ## Run all API tests including integration (needs Postgres + Redis)
	cd $(API_DIR) && $(PYTHON) -m pytest tests -q

lint: ## Lint the API with ruff
	ruff check $(API_DIR)/app $(API_DIR)/tests

format: ## Format the API with ruff
	ruff format $(API_DIR)/app $(API_DIR)/tests

typecheck: ## Type-check the API with pyright
	cd $(API_DIR) && pyright app

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
