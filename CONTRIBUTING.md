We welcome contributions to this project!

Before working on changes, please consider [opening an issue](https://github.com/canonical/charmlint/issues) explaining your use case. If you would like to chat with us about your use cases or proposed implementation, you can reach us on [Matrix](https://matrix.to/#/#charmhub-charmdev:ubuntu.com) or [Discourse](https://discourse.charmhub.io/).

<!--
For detailed dev-environment setup, build, and test instructions, link here to
the substantive doc if one exists (HACKING.md, docs/contributing.md, etc.).
Most Charm Tech repos keep this section inline rather than redirecting.
-->

# Project status

charmlint is early work, and the implementation is subject to change (and probably will change). Please don't treat anything under `src/` as settled, or build on it expecting the internals to stay where they are.

What we're trying to get right at the moment is the set of rules. That's where the care goes: what each rule is for, what it does and doesn't match, and the tests that pin that behaviour down. The tests themselves might change shape later - we'd like them to be less Python-specific, since charmlint is meant to be model-agnostic - so it's not worth over-investing in the current fixtures.

The code is almost entirely agent-generated, and that's likely to continue for a while yet.

# Review

Review still matters, but the weight isn't spread evenly.

Most of the attention belongs on the rule itself:

* Is this a good thing to have a rule about at all? A rule that's noisy, or that encodes a personal preference rather than a practice we'd defend, costs more than it's worth.
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

<!--
Most Charm Tech repos that produce a release artefact include a section
describing how to cut one. The shape depends on what the repo produces:

- PyPI package (uv build → Trusted Publishing): tag → GitHub Release →
  release workflow publishes via pypa/gh-action-pypi-publish (OIDC).
- snap (snapcraft / launchpad build recipe): document the release channel
  promotion flow (edge → beta → candidate → stable).
- Go binary (goreleaser): document `git tag vX.Y.Z && git push --tags`
  and which workflow goreleaser runs from.
- Charm on Charmhub (charmcraft): document the track/channel and the
  upload-resource / promote-charm flow.
- Library shipped via canonical/charmlibs: document the version-bump and
  publish-library flow.

Replace this comment with the actual procedure. Repos that don't produce a
discrete release artefact (demos, tutorials, specs, registries) can drop the
whole section.
-->
