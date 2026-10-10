.PHONY: install check lint fmt type test live bench-validate bench bench-smoke

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

live:  ## check agent + simulator connections from .env
	uv run python -m bazaar.bench ping

bench-validate:  ## replay every task's answer key (no LLM calls)
	uv run python -m bazaar.bench validate

bench-smoke:  ## 3 tasks, 1 trial: check your setup before a full run
	uv run python -m bazaar.bench run --ids T01,T11,T18 --trials 1

bench:  ## full v0 run, 3 trials per task
	uv run python -m bazaar.bench run --trials 3
