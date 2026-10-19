.PHONY: up down test test-backend test-sdk test-frontend migrate demo

up:
	docker compose up --build

down:
	docker compose down

test: test-backend test-sdk test-frontend

test-backend:
	cd backend && .venv/bin/pytest -q

test-sdk:
	cd sdk/python && ../../backend/.venv/bin/pytest -q

test-frontend:
	cd frontend && npm test

migrate:
	cd backend && .venv/bin/alembic upgrade head

demo:
	cd backend && .venv/bin/python -m app.demo
