.DEFAULT_GOAL := help

.PHONY: help lint fmt test lock

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

lint:  ## Lint with ruff and type-check with ty
	uv run --group dev ruff check src tests
	uv run --group dev ruff format --check src tests
	uv run --group dev ty check src tests

format:  ## Format code with ruff
	uv run --group dev ruff format src tests
	uv run --group dev ruff check --fix src tests

test:  ## Run unit tests
	uv run --group dev pytest tests/ --cov=charmlint --cov-report=term-missing

lock:  ## Refresh uv.lock
	uv lock
