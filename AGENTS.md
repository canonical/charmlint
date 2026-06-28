# AGENTS.md

## What this repo is

`charmlint` is a charm-aware, model-agnostic linter for [Juju](https://juju.is/) charms — rules check charm source code against Canonical's charm best practices (observability, security, testing, metadata, configuration).

## Dev setup

```bash
uv sync --dev
```

## Tests

```bash
uv run --group dev pytest
```

## Lint

```bash
uv run --group dev ruff check src tests
uv run --group dev ruff format --check src tests
uv run --group dev ty check src tests
```

`pre-commit` runs the same tools through `uv run` (config in `.pre-commit-config.yaml`); tool versions live in `pyproject.toml`'s `dev` dependency group.

## Conventions

- Commits and PR titles follow [Conventional Commits](https://www.conventionalcommits.org/); PR-title types enforced by `.github/workflows/validate-pr-title.yaml` (see [CONTRIBUTING.md](CONTRIBUTING.md#pull-requests) for the list).
- Rule IDs follow `PREFIX###` — see [docs/id-scheme.md](docs/id-scheme.md) for the prefix catalogue.
- Runtime dependencies are kept minimal (PyYAML only); the `_pypi_attest/` helper is stdlib-only by design.

## Security

See [SECURITY.md](SECURITY.md).
