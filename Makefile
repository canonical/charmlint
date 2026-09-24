.DEFAULT_GOAL := help

.PHONY: help lint format test docs docs-check lock

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

docs:  ## Regenerate docs/rules.md from the rule registry
	uv run python tools/generate_rules_doc.py

docs-check:  ## Fail if docs/rules.md is out of date
	uv run python tools/generate_rules_doc.py --check

lock:  ## Refresh uv.lock
	uv lock
