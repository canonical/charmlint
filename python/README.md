# charmlint — Python implementation

A charm-aware linter for Juju charms, implemented in Python 3.12+.

## Extraction note

Extracted from [`tonyandrewmeyer/cantrip`](https://github.com/tonyandrewmeyer/cantrip)
at path `src/charmlint/` (plus the bundled `src/pypi_attest/` helper),
commit `d2b15056b1e17a99c3e37130fd10d21ad1ab059d`. Git history was not preserved;
this is a fresh repository.

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

Place `.charmlint.yaml` in the charm directory:

```yaml
select: [COS, META]
ignore: [ATT002]
min_severity: warning
```

## Bundled dependency

The `src/pypi_attest/` package is a small, stdlib-only helper (also
extracted from cantrip) that checks PEP 740 attestation status on PyPI.
It is bundled here to keep charmlint dependency-free except for PyYAML.
