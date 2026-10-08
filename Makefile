.PHONY: up down logs test lint lint-be lint-fe

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

test:
	python3 -m pytest -q

lint: lint-be lint-fe

lint-be:
	ruff check backend tests
	black --check backend tests

lint-fe:
	cd frontend && npm run lint && npm run format
