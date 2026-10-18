# Rhinvoice developer tasks. `make qa` is the quality gate: CI is green only if it passes.
SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

COMPOSE_DEV := docker compose -f compose.yml -f compose.dev.yml
# compose.e2e.yml takes Gotenberg from deploy/compose.yml, whose password must be set to be
# read at all; the test database has its own. Without it a fresh checkout (CI) stops at once.
COMPOSE_E2E := POSTGRES_PASSWORD=e2e docker compose -f compose.e2e.yml
DEV_DATABASE_URL := postgresql+psycopg://rhinvoice:rhinvoice-dev@127.0.0.1:5433/rhinvoice

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# --- Setup -----------------------------------------------------------------------

.PHONY: install
install: ## Install backend and frontend dependencies
	cd backend && uv sync --frozen
	cd frontend && pnpm install --frozen-lockfile

# --- Quality gate ------------------------------------------------------------------

.PHONY: qa
qa: backend-qa frontend-qa api-check e2e backup-qa einvoice-qa docs-qa ## Run every check (backend, frontend, contract, E2E, backup, e-invoices, docs)
	@echo "✔ make qa passed"

.PHONY: docs-qa
docs-qa: ## Docs: types, content rules (WRITING.md), build, links, audit
	cd website/docs && pnpm run check
	cd website/docs && pnpm run build
	cd website/docs && pnpm run check:links
	cd website/docs && pnpm audit --prod --audit-level high

.PHONY: backend-qa
backend-qa: backend-lint backend-types backend-arch backend-test backend-mutation backend-audit ## All backend checks

.PHONY: backend-lint
backend-lint: ## ruff lint + format check
	cd backend && uv run ruff check .
	cd backend && uv run ruff format --check .

.PHONY: backend-types
backend-types: ## mypy --strict and pyright strict
	cd backend && uv run mypy
	cd backend && uv run pyright

.PHONY: backend-arch
backend-arch: ## import-linter layer contracts
	cd backend && uv run lint-imports

.PHONY: backend-test
backend-test: ## pytest incl. PostgreSQL integration and schemathesis, 100 % coverage
	cd backend && uv run pytest --cov --cov-report=term-missing:skip-covered

.PHONY: backend-mutation
backend-mutation: ## mutmut on domain + application, score >= 90 % (CHANGED=origin/dev: only changed modules)
	cd backend && uv run python scripts/mutation.py $(if $(CHANGED),--changed $(CHANGED))

.PHONY: backend-audit
backend-audit: ## pip-audit of the runtime dependencies
	cd backend && uv export --frozen --no-dev --no-emit-project --format requirements-txt > .audit-requirements.txt
	cd backend && uv run pip-audit --requirement .audit-requirements.txt --require-hashes --disable-pip --progress-spinner off
	rm -f backend/.audit-requirements.txt

.PHONY: frontend-qa
frontend-qa: ## Prettier, ESLint, tsc, dependency-cruiser, Vitest (100 %), audit, build
	cd frontend && pnpm run format:check
	cd frontend && pnpm run lint
	cd frontend && pnpm run typecheck
	cd frontend && pnpm exec tsc -p tsconfig.node.json --noEmit
	cd frontend && pnpm run depcruise
	cd frontend && pnpm run test:coverage
	cd frontend && pnpm audit --prod --audit-level high
	cd frontend && pnpm run build

.PHONY: api
api: ## Regenerate openapi.json and the TypeScript client types
	cd backend && uv run python scripts/export_openapi.py > openapi.json
	cd frontend && pnpm exec openapi-typescript ../backend/openapi.json -o src/api/schema.d.ts

.PHONY: api-check
api-check: api ## Fail if the generated API files are out of date
	git diff --exit-code -- backend/openapi.json frontend/src/api/schema.d.ts

.PHONY: e2e
e2e: ## Playwright E2E (incl. axe + visual regression) against the Docker stack (SHARD=2/3: one part)
	E2E_SHARD=$(or $(SHARD),1/1) $(COMPOSE_E2E) up --build --exit-code-from e2e; status=$$?; \
	$(COMPOSE_E2E) down -v --remove-orphans > /dev/null 2>&1; exit $$status

.PHONY: backup-qa
backup-qa: ## shellcheck + backup and restore test against the Docker images
	docker run --rm -v "$(CURDIR)/backup:/mnt:ro" koalaman/shellcheck:v0.11.0 /mnt/rhinvoice-backup.sh /mnt/test.sh
	./backup/test.sh

.PHONY: einvoice-qa
einvoice-qa: ## Validate sample e-invoices: KoSIT (EN 16931, XRechnung), Mustang (ZUGFeRD, PDF/A-3)
	docker run --rm -v "$(CURDIR)/einvoice:/mnt:ro" koalaman/shellcheck:v0.11.0 /mnt/validate.sh /mnt/test.sh
	./einvoice/test.sh

.PHONY: e2e-update
e2e-update: ## Re-create all visual regression screenshots
	rm -rf frontend/e2e/__screenshots__
	$(MAKE) e2e

# --- Development ---------------------------------------------------------------------

.PHONY: dev-db
dev-db: ## Start the development database (localhost:5433) and Gotenberg (localhost:3010)
	$(COMPOSE_DEV) up -d db gotenberg

.PHONY: dev-backend
dev-backend: dev-db ## Run the API with auto-reload on http://127.0.0.1:8000
	cd backend && RHINVOICE_DATABASE_URL=$(DEV_DATABASE_URL) RHINVOICE_COOKIE_SECURE=false \
		uv run rhinvoice migrate
	cd backend && RHINVOICE_DATABASE_URL=$(DEV_DATABASE_URL) RHINVOICE_COOKIE_SECURE=false \
		RHINVOICE_GOTENBERG_URL=http://127.0.0.1:3010 \
		uv run uvicorn --factory rhinvoice.api.dev:app --reload --port 8000

.PHONY: dev-frontend
dev-frontend: ## Run the Vite dev server on http://127.0.0.1:5173 (proxies /api)
	cd frontend && pnpm dev

.PHONY: user
user: ## Create a user in the running Docker stack: make user EMAIL=... NAME=...
	docker compose exec app rhinvoice user create --email "$(EMAIL)" --name "$(NAME)"

# --- Backup (docs/backup.md) -----------------------------------------------------------

.PHONY: demo
demo: ## Fill the running Docker stack (after the first-start wizard) with demo data
	docker compose exec app rhinvoice demo

.PHONY: backup
backup: ## Back up the running Docker stack now
	docker compose exec backup rhinvoice-backup backup manual

.PHONY: snapshots
snapshots: ## List the backups
	docker compose exec backup rhinvoice-backup snapshots

.PHONY: restore
restore: ## Replace the database with a backup: make restore SNAPSHOT=latest (or an ID)
	@test -n "$(SNAPSHOT)" || { echo "usage: make restore SNAPSHOT=latest|<id> (see make snapshots)"; exit 2; }
	docker compose stop app backup
	docker compose run --rm --no-deps backup restore "$(SNAPSHOT)"
	docker compose start app backup
