# charmlint

A charm-aware, model-agnostic linter for [Juju](https://juju.is/) charms.

charmlint checks charm source code against Canonical's charm best practices:
observability, security, testing, metadata, configuration, and more.

## Usage

Run it from PyPI with `uvx`, no install needed:

```bash
uvx charmlint /path/to/charm
```

Or add it to a charm's dev dependencies and run it with `uv run`:

```bash
uv add --dev charmlint
uv run charmlint
```

Common options:

```bash
uvx charmlint --format json .
uvx charmlint --select SECURITY,METADATA-001 .
uvx charmlint --ignore no-readme --strict .
```

`charmlint --help` lists the rest. With `--strict`, warnings exit with code 2;
errors always exit with code 1.

## Configuration

Configure under `[tool.charmlint]` in `pyproject.toml`, or in `charmlint.toml`
/ `.charmlint.toml`:

```toml
[tool.charmlint]
select = ["SECURITY", "METADATA"]
ignore = ["METADATA-002"]
```

Individual findings can be suppressed inline with
`# charmlint: ignore[SECURITY-001]`. See
[docs/configuration.md](docs/configuration.md) for all settings and
suppression directives.

## Documentation

- [docs/id-scheme.md](docs/id-scheme.md) — rule IDs and the category catalogue
- [docs/configuration.md](docs/configuration.md) — configuration and inline suppression
- [docs/versioning.md](docs/versioning.md) — versioning and compatibility policy
- [CONTRIBUTING.md](CONTRIBUTING.md) — development setup, tests, and pull requests
- [SECURITY.md](SECURITY.md) — reporting vulnerabilities

## License

Apache 2.0 — see [LICENSE](LICENSE).
