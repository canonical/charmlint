# charmlint

A charm-aware, model-agnostic linter for [Juju](https://juju.is/) charms.

charmlint checks charm source code against Canonical's Juju charm best practices:
observability (COS integration, ops-tracing), security (PEP 740 PyPI attestations),
testing structure, metadata completeness, configuration quality, and more.

Extracted from [`tonyandrewmeyer/cantrip`](https://github.com/tonyandrewmeyer/cantrip),
where charmlint grew as an internal component of the Cantrip AI charm builder.

## Installation

```bash
uv sync --dev
```

## Usage

```bash
uv run charmlint /path/to/charm
uv run charmlint --format json /path/to/charm
uv run charmlint --select COS,META /path/to/charm
uv run charmlint --ignore ATT002 --strict /path/to/charm
```

Or install and run directly:

```bash
uv run pip install -e .
charmlint /path/to/charm
```

## Running tests

```bash
uv run pytest tests/ -v
```

## Rule catalogue

Rule IDs follow `CATEGORY-###` (for example `SECURITY-001`,
`METADATA-003`). See [docs/id-scheme.md](docs/id-scheme.md) for the full
category catalogue and naming rules.

## Configuration

Configure under `[tool.charmlint]` in `pyproject.toml`, or in a standalone
`charmlint.toml` / `.charmlint.toml`. Discovery walks up from the charm
directory, in the manner of ruff.

```toml
[tool.charmlint]
severity = "warning"  # minimum severity to report
select = ["OBSERVABILITY", "METADATA"]
ignore = ["ATTESTATION-002"]

[tool.charmlint.per-rule-severity]
"OBSERVABILITY-005" = "error"
```

## License

Apache 2.0 — see [LICENSE](LICENSE).
