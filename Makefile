.PHONY: help install dev run seed test lint check docker clean
PYTHON ?= python

help:
	@echo "install  Install app dependencies"
	@echo "dev      Install app and development dependencies"
	@echo "run      Start UI and private API"
	@echo "seed     Recreate synthetic sample tables (disposable data only)"
	@echo "test     Run automated tests"
	@echo "lint     Check Python source"
	@echo "check    Run lint and tests"
	@echo "docker   Start Docker Compose"
	@echo "clean    Remove generated Python and tool caches"

install:
	$(PYTHON) -m pip install -r requirements.txt

dev:
	$(PYTHON) -m pip install -r requirements-dev.txt

run:
	$(PYTHON) scripts/start_app.py

seed:
	$(PYTHON) scripts/seed_database.py

test:
	$(PYTHON) -m pytest -q

lint:
	$(PYTHON) -m ruff check app eval tests frontend scripts

check: lint test

docker:
	docker compose up --build

clean:
	find app frontend scripts tests eval -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache .mypy_cache
