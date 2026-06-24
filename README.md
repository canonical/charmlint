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

Rules are grouped by category prefix:

| Prefix | Category |
|--------|----------|
| META   | Metadata completeness |
| DOC    | Documentation quality |
| COS    | Observability / COS integration |
| SEC    | Security |
| ATT    | PyPI attestations (PEP 740) |
| TEST   | Testing structure |
| PEBBLE | Pebble container config |
| REL    | Relation data |
| STATUS | Status handling |
| CONFIG | Configuration quality |
| STRUCT | Repository structure |
| DEP    | Deprecated patterns |
| LIB    | Charm library usage |
| LIBVER | Library version pinning |
| COMPAT | charmcraft.yaml compatibility |

## Configuration

Configure under `[tool.charmlint]` in `pyproject.toml`, or in a standalone
`charmlint.toml` / `.charmlint.toml`. Discovery walks up from the charm
directory, in the manner of ruff.

```toml
[tool.charmlint]
severity = "warning"  # minimum severity to report

[tool.charmlint.lint]
select = ["COS", "META"]
ignore = ["ATT002"]

[tool.charmlint.lint.per-rule-severity]
COS005 = "error"
STR002 = "off"
```

## Bundled helper

The `src/charmlint/_pypi_attest/` package is a small, stdlib-only helper
(originally a separate package in cantrip) that checks PEP 740 attestation
status on PyPI. It lives inside `charmlint` to keep the project
dependency-free except for PyYAML.

## A future Rust implementation

An earlier Rust implementation lived alongside the Python one but was removed:
maintaining two implementations in lockstep was not sustainable at the current
team size. A Rust port may return in the future for speed once the Python
implementation has stabilised.

## License

Apache 2.0 — see [LICENSE](LICENSE).
