.DEFAULT_GOAL := help

.PHONY: help lint format test rules-doc rules-doc-check docs docs-check lock

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

lint:  ## Lint with ruff and type-check with ty
	uv run --group dev ruff check
	uv run --group dev ruff format --check
	uv run --group dev ty check

format:  ## Format code with ruff
	uv run --group dev ruff format
	uv run --group dev ruff check --fix

test:  ## Run unit tests
	uv run --group dev pytest tests/ --cov=charmlint --cov-report=term-missing

rules-doc:  ## Regenerate docs/reference/rules.md from the rule registry
	uv run python tools/generate_rules_doc.py

rules-doc-check:  ## Fail if docs/reference/rules.md is out of date
	uv run python tools/generate_rules_doc.py --check

# The old names for the two targets above, kept so existing habits and scripts
# still work.
docs: rules-doc  ## Alias for rules-doc
docs-check: rules-doc-check  ## Alias for rules-doc-check

lock:  ## Refresh uv.lock
	uv lock
