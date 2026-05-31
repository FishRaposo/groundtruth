DOCKER_COMPOSE	:= docker compose
PYTHON			:= python
PIP				:= pip
BACKEND_DIR		:= backend
FRONTEND_DIR	:= frontend

.PHONY: help demo dev dev-down dev-logs build seed reset migrate migrate-create \
        test test-frontend test-all benchmark lint lint-fix format clean install setup \
        shell db-shell

help:
	@echo "GroundTruth - Available targets:"
	@echo ""
	@echo "  demo            Quick demo: start services, seed data, open browser"
	@echo "  dev             Start docker compose in detached mode"
	@echo "  dev-down        Stop docker compose"
	@echo "  dev-logs        Tail docker compose logs"
	@echo "  build           Build docker images"
	@echo "  seed            Run the seed script to load sample data"
	@echo "  reset           Reset database (drop + recreate + seed)"
	@echo "  migrate         Run alembic migrations"
	@echo "  migrate-create  Create a new alembic migration (msg=)"
	@echo "  test            Run backend tests with coverage"
	@echo "  test-frontend   Run frontend tests"
	@echo "  test-all        Run all tests"
	@echo "  lint            Run ruff check + mypy on backend"
	@echo "  lint-fix        Run ruff fix"
	@echo "  format          Run ruff format"
	@echo "  clean           Remove build artifacts and caches"
	@echo "  install         Install backend + frontend deps"
	@echo "  setup           First-time setup (install + build + migrate + seed)"
	@echo "  shell           Open bash in the API container"
	@echo "  db-shell        Open psql in the database container"

demo:
	@echo "🚀 Starting GroundTruth demo..."
	$(DOCKER_COMPOSE) up -d
	@echo "⏳ Waiting for services to be healthy..."
	@sleep 5
	@echo "🌱 Seeding sample data..."
	$(PYTHON) scripts/seed.py --api-url http://localhost:8000 --data-dir ./data/sample || true
	@echo "✅ Demo ready!"
	@echo "   Frontend: http://localhost:3000"
	@echo "   API:      http://localhost:8000"
	@echo "   Docs:     http://localhost:8000/docs"
	@echo ""
	@echo "To stop: make dev-down"

dev:
	$(DOCKER_COMPOSE) up -d

dev-down:
	$(DOCKER_COMPOSE) down

dev-logs:
	$(DOCKER_COMPOSE) logs -f

build:
	$(DOCKER_COMPOSE) build

seed:
	$(PYTHON) scripts/seed.py --api-url http://localhost:8000 --data-dir ./data/sample

reset:
	$(PYTHON) scripts/reset_db.py --confirm --seed

migrate:
	cd $(BACKEND_DIR) && alembic upgrade head

migrate-create:
	cd $(BACKEND_DIR) && alembic revision --autogenerate -m "$(msg)"

test:
	cd $(BACKEND_DIR) && $(PYTHON) -m pytest --cov=app --cov-report=term-missing -v

test-frontend:
	cd $(FRONTEND_DIR) && npm test

test-all: test test-frontend

benchmark:
	$(PYTHON) scripts/benchmark.py

lint:
	cd $(BACKEND_DIR) && ruff check . && mypy app

lint-fix:
	cd $(BACKEND_DIR) && ruff check --fix .

format:
	cd $(BACKEND_DIR) && ruff format .

clean:
	$(PYTHON) -c "import shutil, glob; \
		dirs = glob.glob('**/__pycache__', recursive=True) + \
		       glob.glob('**/.pytest_cache', recursive=True) + \
		       glob.glob('**/*.egg-info', recursive=True); \
		[shutil.rmtree(d) for d in dirs if __import__('pathlib').Path(d).exists()]"
	$(PYTHON) -c "import pathlib; \
		[p.unlink() for p in pathlib.Path('.').rglob('.coverage')]"
	rm -rf $(FRONTEND_DIR)/.next
	rm -rf $(FRONTEND_DIR)/node_modules/.cache

install:
	cd $(BACKEND_DIR) && $(PIP) install -e ".[dev]"
	cd $(FRONTEND_DIR) && npm install

setup: install build migrate seed

shell:
	$(DOCKER_COMPOSE) exec api bash

db-shell:
	$(DOCKER_COMPOSE) exec db psql -U groundtruth -d groundtruth
