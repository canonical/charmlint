# AGENTS.md

## What this repo is

`charmlint` is a linter for [Juju](https://canonical.com/juju) charms — rules check charm source code against Canonical's charm best practices (observability, security, testing, metadata, configuration). It is model-agnostic: nothing in it should depend on, or assume, a particular AI assistant or model (Claude Code, Copilot, OpenAI, …). It complements general-purpose tools like ruff and pyright rather than replacing them: a rule belongs here only if it needs knowledge of charms, Juju, or Canonical practice. If a generic Python linter or type checker could catch it, it doesn't belong in charmlint.

## Dev setup

```bash
uv sync
```

## Tests

```bash
uv run pytest
```

Tests that need the network (the reference-URL checks) are deselected by default; run them with `-m network`.

## Lint

```bash
uv run ruff check
uv run ruff format --check
uv run ty check
```

`pre-commit` runs the same tools through `uv run` (config in `.pre-commit-config.yaml`); tool versions live in `pyproject.toml`'s `dev` dependency group.

## Rule reference

`docs/rules.md` is generated from the rule registry — its ID, name, default severity, description, reference URL and class docstring. Run `make docs` after adding or changing a rule; CI fails if the page is stale. Never hand-edit the page: a rule's docstring is the text that appears on it, so improve it there.

## Corpus measurements

A new or changed rule needs a TP/FP table over the hyrum cache (`~/.cache/hyrum/charms`) before review. Enumerate charms and report results as described in [docs/corpus.md](docs/corpus.md) — the cache contains build trees and mirrored repos, so an ad-hoc `rglob` gives a different denominator every time (~1970 directories vs 655 charms).

## Conventions

- Commits and PR titles follow [Conventional Commits](https://www.conventionalcommits.org/); PR-title types enforced by `.github/workflows/validate-pr-title.yaml` (see [CONTRIBUTING.md](CONTRIBUTING.md#pull-requests) for the list).
- Rule IDs follow `CATEGORY-###` (`SECURITY-001`, `METADATA-003`) — see [docs/id-scheme.md](docs/id-scheme.md) for the category catalogue.
- Runtime dependencies are kept minimal (PyYAML only); the `_pypi_attest.py` helper is stdlib-only by design.

## Rule module layout

Rule modules are read far more often in review than they are written, so lay one
out top-down and let the reader follow the call graph without scrolling back:

- Rule classes first, in rule-ID order.
- Then the helpers, in the order they are first called: a helper is defined below
  its caller, and two helpers appear in the order the caller reaches them.
- A helper used by one rule module stays private to it. A concern shared across
  rule modules belongs in `_ast.py` or `_yaml.py` instead — check there before
  writing a new walker or parser.

## Security

See [SECURITY.md](SECURITY.md).
