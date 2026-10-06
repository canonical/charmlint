We welcome contributions to this project!

Before working on changes, please consider [opening an issue](https://github.com/canonical/charmlint/issues) explaining your use case. If you would like to chat with us about your use cases or proposed implementation, you can reach us on [Matrix](https://matrix.to/#/#charmhub-charmdev:ubuntu.com) or [Discourse](https://discourse.charmhub.io/).

All contributors must sign the [Canonical contributor licence agreement](https://ubuntu.com/legal/contributors), which grants Canonical permission to use the contributions. You retain copyright ownership of your contributions (no copyright assignment).

# Development

Set up a dev environment and run the tests with [uv](https://docs.astral.sh/uv/):

```bash
uv sync
uv run pytest
```

Lint, format, and type-check:

```bash
uv run ruff check
uv run ruff format --check
uv run ty check
```

`pre-commit` runs the same checks (config in `.pre-commit-config.yaml`).

A new or changed rule needs measurements over the charm corpus before review - see [docs/corpus.md](docs/corpus.md).

[docs/rules.md](docs/rules.md) is generated from the rule registry (CI fails if it's stale). After adding or changing a rule, regenerate it with `make docs`. Don't edit the page by hand; improve the rule docstrings instead.

# Develop in a workshop

[Workshop](https://ubuntu.com/workshop) definitions live in `.workshop/`. The `dev` workshop is a container with `uv`, `make`, and charmlint's development dependencies, so you don't need to install any of them on the host:

```bash
sudo snap install workshop --classic  # If you don't have it already.
workshop launch dev
workshop run dev lint
```

The actions run the `make` targets with the same names: `format`, `lint`, `test`, `docs`, and `docs-check`. The workshop keeps its virtual environment outside the project directory, so it doesn't share or overwrite the `.venv` on your host.

# Project status

charmlint is early work, and the implementation is subject to change (and probably will change). Please don't treat anything under `src/` as settled, or build on it expecting the internals to stay where they are.

What we're trying to get right at the moment is the set of rules. That's where the care goes: what each rule is for, what it does and doesn't match, and the tests that pin that behaviour down. The tests themselves might change shape later - we'd like them to be less Python-specific, since charmlint is meant to work with any AI model or coding agent, not just one - so it's not worth over-investing in the current fixtures.

The code is almost entirely agent-generated, and that's likely to continue for a while yet.

# Review

Review still matters, but the weight isn't spread evenly.

Most of the attention belongs on the rule itself:

* Is this a good thing to have a rule about at all? A rule that's noisy, or that encodes a personal preference rather than a practice we'd defend, costs more than it's worth.
* Does it need to know about charms? charmlint complements general-purpose tools like ruff and pyright rather than replacing them - if a generic Python linter or type checker could catch it, it belongs there instead.
* What does it match, and (more importantly) what does it not match? A false positive is worse than a gap.
* Do the tests actually capture that? A test that only exercises the case the rule was written for isn't telling us much.

The implementation gets a lighter pass. We're more lenient about "agent-isms" here than in the other Charm Tech repos: if the code is more verbose or more defensive than a person would have written it, and it's correct and readable, that's ok. That's not a license to let quality slide - we still want code we'd be happy to maintain, and unnecessary comments (especially ones referring to history) should still go. But if you find yourself choosing, spend the time on the rule rather than on the style of the code implementing it.

# AI

You're welcome to submit pull requests that are partly or entirely generated using generative AI tools. However, you must review the code yourself before moving the PR out of draft -- by submitting the PR, you are claiming personal responsibility for its quality and suitability. If you are not capable of reviewing the PR, please do not submit it (maybe you'd like to open an issue instead). PRs that are clearly (co-)authored by tools will be closed without review unless there is a human author that claims responsibility for the PR.

Please do not use tools (such as GitHub Copilot) to provide PR reviews. The Charm Tech team also has access to these tools, and will use them when appropriate.

# Pull requests

Changes are proposed as [pull requests on GitHub](https://github.com/canonical/charmlint/pulls).

- Work on a branch in your own fork.
- Sequence your commits logically if possible. But don't worry too much -- we'll squash to `main` after review.
- Don't force-push after review has started.
- Follow [conventional commit style](https://www.conventionalcommits.org/en/) for the PR title (not required for individual commits).

The allowed PR-title types — enforced by `.github/workflows/validate-pr-title.yaml` — are:

`chore`, `ci`, `docs`, `feat`, `fix`, `perf`, `refactor`, `revert`, `test`

Examples:

- feat: add support for X
- fix!: correct the type hinting for config data
- docs: clarify how to use Y
- ci: tighten the publish workflow

We consider this project too small to use scopes, so we don't use them.

## Branch updates

Before you ask for review, please rebase your branch onto `main` so that your changes will merge cleanly.

If you need to bring in the latest changes from `main` after the review has started, please use a merge commit.

# Releasing

charmlint is published to [PyPI](https://pypi.org/project/charmlint/) by `.github/workflows/publish.yaml`, with Trusted Publishing, whenever a `v*` tag is pushed.

1. Work out the new version from [docs/versioning.md](docs/versioning.md): a minor bump if anything since the last release adds a rule or changes what a rule reports, and a patch bump otherwise.
2. Open a PR that bumps the version (`uv version --bump minor` or `--bump patch` updates both `pyproject.toml` and `uv.lock`), titled like `chore: bump version to 0.3.0`, and merge it.
3. Create a GitHub release on the merge commit, with a new `vX.Y.Z` tag that matches the version and a short summary of what changed. Creating the release pushes the tag, which starts the publish workflow.
4. Check that the publish run succeeds. It stops before building if the tag doesn't match the version in `pyproject.toml`. If that happens, don't move the tag (the tag ruleset won't let you anyway) - bump the patch version and release again.

To try the workflow out without releasing anything, run it manually from the Actions tab. A manual run publishes a `.devN` build to TestPyPI instead.
