# charmlint

A charm-aware, model-agnostic linter for [Juju](https://juju.is/) charms.

charmlint checks charm source code against Canonical's Juju charm best practices:
observability (COS integration, ops-tracing), security (PEP 740 PyPI attestations),
testing structure, metadata completeness, configuration quality, and more.

## Implementations

Two reference implementations live side by side in this repository:

| Directory | Language | Entry point |
|-----------|----------|-------------|
| `python/` | Python 3.12+ | `charmlint` CLI / `charmlint` package |
| `rust/`   | Rust 2021  | `charmlint` binary via `cargo build` |

Both implementations share the same rule catalogue, diagnostic model, and
`.charmlint.yaml` configuration format.  They were extracted from
[`tonyandrewmeyer/cantrip`](https://github.com/tonyandrewmeyer/cantrip)
where charmlint grew as an internal component of the Cantrip AI charm builder.

## Quick start

**Python:**
```bash
cd python
uv sync --dev
uv run charmlint /path/to/your/charm
```

**Rust:**
```bash
cd rust
cargo build --release
./target/release/charmlint /path/to/your/charm
```

## Configuration

Both implementations read `.charmlint.yaml` from the charm directory:

```yaml
select: [COS, META, SEC]   # categories to enable (omit for all)
ignore: [DOC003, ATT002]   # rule IDs or categories to skip
min_severity: warning       # error | warning | info
```

## License

Apache 2.0 — see [LICENSE](LICENSE).
