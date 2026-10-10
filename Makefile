.PHONY: install check lint fmt type test live

install:
	uv sync

check: lint type test  ## everything CI runs

lint:
	uv run ruff check .
	uv run ruff format --check .

fmt:
	uv run ruff check --fix .
	uv run ruff format .

type:
	uv run mypy src tests

test:
	uv run pytest

live:  ## one real call to the endpoint in .env
	BAZAAR_RUN_LIVE=1 uv run pytest -m live
