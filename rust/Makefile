.DEFAULT_GOAL := help

.PHONY: help lint fmt test build

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

lint:  ## Lint with clippy and check formatting
	cargo fmt --all -- --check
	cargo clippy --all-targets --all-features -- -D warnings

fmt:  ## Format code with rustfmt
	cargo fmt --all

test:  ## Run unit and integration tests
	cargo test --all-features

build:  ## Build release binary
	cargo build --release
