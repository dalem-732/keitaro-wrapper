.PHONY: install migrate run dev-front build test lint check docker-up docker-down

BACK = cd backend &&

install:        ## зависимости бэкенда и фронтенда
	$(BACK) uv sync
	cd frontend && npm ci

migrate:        ## применить миграции (DATABASE_URL из .env, по умолчанию SQLite)
	$(BACK) uv run alembic upgrade head

build:          ## собрать фронтенд (FastAPI раздаёт frontend/dist)
	cd frontend && npm run build

run: migrate    ## запустить приложение на http://127.0.0.1:8000
	$(BACK) uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

dev-front:      ## фронтенд с hot reload на http://127.0.0.1:5173 (прокси /api → :8000)
	cd frontend && npm run dev

test:           ## тесты бэкенда
	$(BACK) uv run pytest -q

lint:           ## линтеры и проверка типов
	$(BACK) uv run ruff check . && uv run ruff format --check . && uv run mypy app
	cd frontend && npx oxlint src && npx tsc -b

check: lint test

docker-up:      ## приложение + PostgreSQL в Docker
	docker compose up --build -d

docker-down:
	docker compose down
