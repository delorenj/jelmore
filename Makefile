# THIS MAKEFILE SHOULD BE DEPRECATED. 
# USE `mise tasks` INSTEAD.
# 
.PHONY: help install setup docker-up docker-down migrate dev test clean

help:
	@echo "Available commands:"
	@echo "  make install    - Install dependencies"
	@echo "  make setup      - Full setup (docker + deps)"
	@echo "  make docker-up  - Start Docker services"
	@echo "  make docker-down - Stop Docker services"
	@echo "  make migrate    - Run database migrations"
	@echo "  make dev        - Start development server"
	@echo "  make test       - Run tests"
	@echo "  make clean      - Clean up generated files"

install:
	uv venv
	. .venv/bin/activate && uv pip install -e ".[dev]"

setup: docker-up install
	cp -n .env.example .env || true
	@echo "✅ Setup complete! Run 'make dev' to start the server"

docker-up:
	docker-compose up -d
	@echo "Waiting for services to be healthy..."
	@sleep 5

docker-down:
	docker-compose down

migrate:
	. .venv/bin/activate && alembic upgrade head

dev:
	. .venv/bin/activate && uvicorn app.main:app --reload --host 0.0.0.0 --port 8687

test:
	. .venv/bin/activate && pytest

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	rm -rf .ruff_cache
