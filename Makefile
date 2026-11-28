.DEFAULT_GOAL := help

.PHONY: help lint ruff-check ruff-format-check typecheck format test test-network rules-doc rules-doc-check docs-site lock lock-check

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# Extra arguments for pytest, for example: make test PYTEST_ARGS="--maxfail=1 -q"
PYTEST_ARGS ?=

lint: ruff-check ruff-format-check typecheck rules-doc-check lock-check  ## Everything CI's lint job runs: ruff, ty, and the docs and lock checks

ruff-check:  ## Check for lint errors with ruff
	uv run --group dev ruff check

ruff-format-check:  ## Check formatting with ruff
	uv run --group dev ruff format --check

typecheck:  ## Type-check with ty
	uv run --group dev ty check

format:  ## Apply safe lint fixes, then format code with ruff
	uv run --group dev ruff check --fix
	uv run --group dev ruff format

test:  ## Run unit tests
	uv run --group dev pytest --cov=charmlint --cov-report=term-missing $(PYTEST_ARGS)

test-network:  ## Run the tests that need internet access (reference URLs)
	uv run --group dev pytest -m network

rules-doc:  ## Regenerate docs/reference/rules.md from the rule registry
	uv run python tools/generate_rules_doc.py

rules-doc-check:  ## Fail if docs/reference/rules.md is out of date
	uv run python tools/generate_rules_doc.py --check

# The Sphinx targets (html, spelling, linkcheck, ...) are in docs/Makefile;
# `make docs-site` builds the site from here.
docs-site:  ## Build the documentation site (runs `make html` in docs/)
	$(MAKE) -C docs html

lock:  ## Refresh uv.lock
	uv lock

lock-check:  ## Fail if uv.lock is out of date
	uv lock --check
