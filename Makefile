.PHONY: help test test-unit test-coverage lint clean run-setup db-schema db-reset

# ── Variables ─────────────────────────────────────────────────────────────────
PYTHON ?= python
VENV ?= .venv
PSQL ?= psql

# ── Help ───────────────────────────────────────────────────────────────────────
help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ── Development ────────────────────────────────────────────────────────────────
test: ## Run all unit tests
	$(PYTHON) -m pytest tests/unit/ -v --tb=short

test-unit: ## Run unit tests (quiet output)
	$(PYTHON) -m pytest tests/unit/ -q

test-coverage: ## Run tests with coverage report
	$(PYTHON) -m pytest tests/unit/ --cov=src --cov-report=term-missing --cov-report=html

lint: ## Run ruff linter
	ruff check src/

format: ## Run ruff formatter
	ruff format src/ tests/

clean: ## Remove build artifacts and caches
	rm -rf .pytest_cache .coverage htmlcov/ __pycache__/ src/__pycache__/ \
	       .venv/ venv/ build/ dist/ *.egg-info/

# ── Database ─────────────────────────────────────────────────────────────────
db-schema: ## Apply DB schema (set DATABASE_URL first)
	$(PSQL) "$$DATABASE_URL" -f src/db/schema.sql

db-reset: ## Drop and recreate database schema (DANGEROUS — use only locally)
	$(PSQL) "$$DATABASE_URL" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
	$(MAKE) db-schema

# ── Setup ─────────────────────────────────────────────────────────────────────
run-setup: ## Show the droplet setup command
	@echo "Run this on a fresh DigitalOcean droplet:"
	@echo "  curl -sSL https://raw.githubusercontent.com/SeanConway102/google-ads-agent-api/main/setup_droplet.sh | bash"

# ── CI ────────────────────────────────────────────────────────────────────────
ci-local: ## Run the full CI pipeline locally (same as GitHub Actions)
	$(MAKE) lint
	$(MAKE) test
