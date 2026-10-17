# Common tasks. Database targets use MIGRATE_DATABASE_URL (defaults to the compose db).
MIGRATE_DATABASE_URL ?= postgres://app:app@localhost:5432/app?sslmode=disable
MIGRATE ?= migrate

.PHONY: up down db migrate-up migrate-down db-check seed api web test lint

up:            ## whole stack on http://localhost:8080
	docker compose up --build

down:
	docker compose down

db:            ## only Postgres + migrations, for running api/web on the host
	docker compose up -d db migrate

migrate-up:
	$(MIGRATE) -path migrations -database "$(MIGRATE_DATABASE_URL)" up

migrate-down:  ## one step back
	$(MIGRATE) -path migrations -database "$(MIGRATE_DATABASE_URL)" down 1

db-check:      ## CI's up -> smoke -> down -> up; needs an EMPTY database
	MIGRATE=$(MIGRATE) MIGRATE_DATABASE_URL="$(MIGRATE_DATABASE_URL)" scripts/db-check.sh

seed:
	cd backend && uv run python -m app.cli seed

api:           ## backend on :8000 with reload
	cd backend && uv run uvicorn app.main:app --reload --port 8000

web:           ## frontend on :5173, proxies /api to :8000
	cd frontend && npm run dev

test:
	cd backend && uv run pytest -q
	cd frontend && npm run test

lint:
	cd backend && uv run ruff check . && uv run ruff format --check .
	cd frontend && npm run lint:check && npm run type-check
