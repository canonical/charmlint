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

### In GitHub Actions

`--format github` prints each finding as a workflow command, so it shows up as an annotation on the pull request's diff:

```yaml
- uses: astral-sh/setup-uv@07a047e608db84b3d8c06cd9a7c7dcc9c355c18e  # v10.3.2
- run: uvx charmlint --format github --strict .
```

GitHub shows at most 10 error and 10 warning annotations per step. To keep every finding, and track them over time, use `--format sarif` and upload the result to code scanning:

```yaml
- run: uvx charmlint --format sarif . > charmlint.sarif
- uses: github/codeql-action/upload-sarif@9b3254085494b55a0f7c4c2b3d2d52cc712ce370  # v4.39.1
  if: always()
  with:
    sarif_file: charmlint.sarif
    category: charmlint
```

If you run charmlint separately for each charm, for example in a matrix, give each upload its own `category`.

An error makes the charmlint step fail. To make code scanning the only signal, set `continue-on-error: true` on that step.

Uploading needs the `security-events: write` permission. A private repository also needs the `contents: read` permission and GitHub Advanced Security.

Both formats name files relative to the repository root, whichever directory you lint and whatever the step's `working-directory`. Outside GitHub Actions, they're relative to the current directory.

### In Test Observer

`--format junit` prints JUnit XML for uploading to [Test Observer](https://github.com/canonical/test_observer), with a test case for each rule:

```yaml
- run: uvx charmlint --format junit . > charmlint.xml
```

Each charm is a test suite named `charmlint`. It has a test case for every rule, named `charmlint/` and the rule ID, and one named `charmlint/FATAL`. A rule's test case fails when the rule finds something that fails the run: an error, or a warning with `--strict`. All the rule's findings are in its `system-out`. A rule that didn't run is skipped. A suppressed finding doesn't count. If charmlint can't load the charm, `charmlint/FATAL` is an error and every rule is skipped. Files are named relative to the repository root, as in the GitHub formats.

A failing run fails the charmlint step, so give the step that uploads the file `if: always()`.

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
