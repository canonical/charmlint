We welcome contributions to this project!

Before working on changes, please consider [opening an issue](https://github.com/canonical/charmlint/issues) explaining your use case. If you would like to chat with us about your use cases or proposed implementation, you can reach us on [Matrix](https://matrix.to/#/#charmhub-charmdev:ubuntu.com) or [Discourse](https://discourse.charmhub.io/).

All contributors must sign the [Canonical contributor licence agreement](https://ubuntu.com/legal/contributors), which grants Canonical permission to use the contributions. You retain copyright ownership of your contributions (no copyright assignment).

# Development

Set up a dev environment and run the tests with [uv](https://docs.astral.sh/uv/):

```bash
uv sync
uv run pytest
```

Tests that need the network (the reference-URL checks) are deselected by default; run them with `uv run pytest -m network`.

Lint, format, and type-check:

```bash
uv run ruff check
uv run ruff format --check
uv run ty check
```

`pre-commit` runs the same checks (config in `.pre-commit-config.yaml`).

A new or changed rule needs measurements over the charm corpus before review - see [docs/corpus.md](docs/corpus.md).

[docs/rules.md](docs/rules.md) is generated from the rule registry (CI fails if it's stale). After adding or changing a rule, regenerate it with `make docs`. Don't edit the page by hand; improve the rule docstrings instead.

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

Two workflows make a release, and you decide twice: once when you review the version-bump PR, and once when you publish the draft release. Nothing reaches PyPI until you publish the draft, so an abandoned attempt costs at most a branch and a draft to delete. Releases only come from `main`.

## 1. Propose the release

Run the ["Propose a release"](https://github.com/canonical/charmlint/actions/workflows/propose-release.yaml) workflow from `main`. It takes two inputs:

- `version`: leave this empty for an ordinary release. The workflow counts from the last `v*` tag and reads the conventional commits since then: a `feat` or a breaking change makes it a minor release, and anything else makes it a patch release. That's close to [docs/versioning.md](docs/versioning.md), but not the same: a `fix` that makes a rule report more is a minor release there, and a `feat` that only adds a CLI flag is a patch release. Fill this in when the commits won't give the right answer, or for a pre-release such as `0.3.0rc1`. What you type is used as it stands.
- `dry_run`: do everything except push the branch and open the PR. The proposed version, the changelog entry and the drafted notes go in the run summary.

The workflow writes the [CHANGES.md](CHANGES.md) entry, updates the version in `pyproject.toml` and `uv.lock`, drafts the release title and notes, and opens a PR from a `release-prep-X.Y.Z` branch.

Review both halves of it:

- The diff: the version and the changelog entry. If a commit message needs adjusting in the changelog, edit `CHANGES.md` in this PR: the draft release copies this version's section from there.
- The release title and notes, which are in the PR description under the "Release title" and "Release notes" headings. Edit them there, and keep the hidden `<!-- release-title:start -->`/`<!-- release-notes:start -->` markers (and their `end` partners): that's where the next workflow reads them from. Write only the summary for the title, since the version is added for you. Everything outside the markers is for reviewers and goes no further.

The PR is opened with the workflow's own token, so GitHub won't start the usual checks on it. Close and reopen the PR to get them to run, then merge it once they pass.

## 2. Create the draft release

Once the PR is merged, run the ["Create the draft release"](https://github.com/canonical/charmlint/actions/workflows/create-draft-release.yaml) workflow with the PR's number. It checks that the PR was merged into `main` and changed the version in `pyproject.toml`, then creates a **draft** release on the merge commit, titled with the version and your summary. The body is the notes from the PR description, then this version's section of `CHANGES.md`, an "All commits" link, and a line thanking any contributors from outside the team. A version with an `a`, `b` or `rc` in it is marked as a pre-release.

Nothing is published and the tag doesn't exist yet. Edit the draft if you need to.

## 3. Publish the draft

Publishing the draft creates the `vX.Y.Z` tag, which starts `.github/workflows/publish.yaml`. That publishes to [PyPI](https://pypi.org/project/charmlint/) with Trusted Publishing, and attests the build and its SBOM. It stops before building if the tag doesn't match the version in `pyproject.toml`. If that happens, don't move the tag (the tag ruleset won't let you anyway) - delete the release, and release the next patch version instead.

To try the publish workflow out without releasing anything, run it manually from the Actions tab. A manual run publishes a `.devN` build to TestPyPI instead.

## Settings a repository admin has to create

An environment called `release-notes`, holding an `OPENROUTER_API_KEY` secret and an `OPENROUTER_MODEL` variable. Without them, "Propose a release" puts a placeholder where the notes would go and carries on, and you write the notes yourself in the PR description.
