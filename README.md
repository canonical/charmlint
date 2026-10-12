# charmlint

[![CI](https://github.com/canonical/charmlint/actions/workflows/ci.yaml/badge.svg?branch=main)](https://github.com/canonical/charmlint/actions/workflows/ci.yaml)
[![PyPI](https://img.shields.io/pypi/v/charmlint)](https://pypi.org/project/charmlint/)

A linter for [Juju](https://canonical.com/juju) charms.

charmlint checks charm source code against Canonical's charm best practices: observability, security, testing, metadata, configuration, and more. It's for charm authors and reviewers who want best-practice gaps caught before review rather than during it, locally or in CI. It isn't tied to any AI assistant or model: it works the same whether you run it yourself or from Claude Code, Copilot, Codex, or any other coding agent.

## Usage

charmlint requires Python 3.12 or later. Run it from PyPI with `uvx`, no install needed:

```bash
uvx charmlint /path/to/charm
```

Or add it to a charm's dev dependencies and run it with `uv run`:

```bash
uv add --dev charmlint
uv run charmlint
```

charmlint doesn't follow SemVer: a minor release can add or tighten rules, so an upgrade may turn a clean run into a failing one. If you set version bounds, see [docs/versioning.md](docs/versioning.md#pinning-charmlint) for how to pin.

Common options:

```bash
uvx charmlint --format json .
uvx charmlint --select SECURITY,METADATA-001 .
uvx charmlint --ignore no-readme --strict .
```

`charmlint --help` lists the rest. Errors cause charmlint to exit with code 1. With `--strict`, warnings cause charmlint to exit with code 2.

## Configuration

Configure under `[tool.charmlint]` in `pyproject.toml`:

```toml
[tool.charmlint]
select = ["SECURITY", "METADATA"]
ignore = ["METADATA-002"]
```

You can also use a standalone `charmlint.toml` or `.charmlint.toml` file, with the same keys at the top level (no `[tool.charmlint]` header).

Individual findings can be suppressed inline with `# charmlint: ignore[SECURITY-001]`. See [docs/configuration.md](docs/configuration.md) for all settings and suppression directives.

## Documentation

- [docs/rules.md](docs/rules.md) — every rule and what it checks for
- [docs/id-scheme.md](docs/id-scheme.md) — rule IDs and the category catalogue
- [docs/configuration.md](docs/configuration.md) — configuration and inline suppression
- [docs/versioning.md](docs/versioning.md) — versioning and compatibility policy
- [SECURITY.md](SECURITY.md) — reporting vulnerabilities

## Community and support

Questions and discussion are welcome on [Matrix](https://matrix.to/#/#charmhub-charmdev:ubuntu.com) and [Discourse](https://discourse.charmhub.io/). If you find a bug or have a feature request, please open a [GitHub issue](https://github.com/canonical/charmlint/issues). Everyone taking part is expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Contributing

Improvements to the rules, the code, and the documentation are all welcome. [CONTRIBUTING.md](CONTRIBUTING.md) covers development setup, tests, and pull requests. Contributors need to sign the [Canonical contributor licence agreement](https://ubuntu.com/legal/contributors).
