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

## Suppressing findings inline

Individual findings can be silenced from within a charm's YAML files with
ruff-style `# noqa` comments.

An inline `# noqa` suppresses every finding reported on that line; add a
comma-separated list of codes to suppress only those. A code is a full
rule ID (`SECURITY-001`) or a category (`SECURITY`):

```yaml
config:
  options:
    admin-password:  # noqa: SECURITY-001
      type: string
```

A file-level `# charmlint: noqa` (on any line) suppresses the whole file;
`# charmlint: noqa: SECURITY-001` suppresses only the listed rules across
the file:

```yaml
# charmlint: noqa: SECURITY-001
```

Inline `# noqa` only applies to findings that carry a line number (the
per-config-option rules today); file-anchored findings are silenced with
a file-level directive. Only YAML files are scanned.

## License

Apache 2.0 — see [LICENSE](LICENSE).
