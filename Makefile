.DEFAULT_GOAL := help

.PHONY: help lint for,at test lint-python lint-rust format-python format-rust test-python test-rust

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'

lint: lint-python lint-rust  ## Lint both the Python and Rust implementations

fmt: fmt-python fmt-rust  ## Format both the Python and Rust implementations

test: test-python test-rust  ## Run unit tests for both implementations

lint-python:  ## Lint the Python implementation
	$(MAKE) -C python lint

lint-rust:  ## Lint the Rust implementation
	$(MAKE) -C rust lint

format-python:  ## Format the Python implementation
	$(MAKE) -C python format

format-rust:  ## Format the Rust implementation
	$(MAKE) -C rust format

test-python:  ## Run Python unit tests
	$(MAKE) -C python test

test-rust:  ## Run Rust tests
	$(MAKE) -C rust test
