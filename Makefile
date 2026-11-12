.DEFAULT_GOAL := help

.PHONY: help lint format test docs docs-check lock

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

lint:  ## Lint with ruff and type-check with ty, for example: make lint ARGS='src/charmlint/_cli.py'
	uv run --group dev ruff check
	uv run --group dev ruff format --check
	uv run --group dev ty check $(ARGS)

format:  ## Format code with ruff
	uv run --group dev ruff format
	uv run --group dev ruff check --fix

test:  ## Run unit tests, for example: make test ARGS='-k test_cli'
	uv run --group dev pytest $(ARGS) tests/ --cov=charmlint --cov-report=term-missing $(if $(ARGS),--cov-fail-under=0)

docs:  ## Regenerate docs/rules.md from the rule registry
	uv run python tools/generate_rules_doc.py

docs-check:  ## Fail if docs/rules.md is out of date
	uv run python tools/generate_rules_doc.py --check

lock:  ## Refresh uv.lock
	uv lock
