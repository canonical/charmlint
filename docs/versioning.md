# Versioning

charmlint uses a versioning scheme modelled on [ruff's](https://docs.astral.sh/ruff/versioning/). If you are familiar with ruff, charmlint's version numbers should behave the way you expect: the **minor** version number is used for breaking changes and the **patch** version number is used for bug fixes.

This is *not* [SemVer](https://semver.org). We use a custom scheme — `major.minor.patch` — with the following meaning:

- **major** — reserved for large, deliberate overhauls of charmlint. Do not expect major version bumps on a regular cadence.
- **minor** — a breaking change (see below).
- **patch** — a bug fix or other backwards-compatible change (see below).

Because the minor version carries breaking changes, a bump from, say, `0.4.7` to `0.5.0` may require action on your part, while `0.4.7` to `0.4.8` should always be safe.

## Why not SemVer?

A linter is unusual: almost every improvement is, strictly speaking, a breaking change. Adding a rule, or teaching an existing rule to catch a new case, can surface diagnostics that were not reported before, which can fail a CI run that was previously green. Under strict SemVer, charmlint could barely publish anything without a major version bump, which would make the major version meaningless.

Instead — exactly as ruff does — we reserve the *minor* version for changes that are likely to break you, and the *patch* version for everything else, including new rules that ship behind [preview mode](#preview-mode).

## What triggers a minor bump (breaking changes)

A new minor version is released when charmlint makes a change that is likely to require action from you. This includes:

### Linter

- Promoting a new rule from preview to stable.
- Changing the behaviour of a stable rule, such that it reports diagnostics it previously did not (or stops reporting ones it did) — for example, broadening what a rule considers a violation.
- Adding a stable rule to, or removing one from, the set of rules enabled by default.
- Removing a rule, or deprecating a rule and removing it in the same release.
- Changing a stable rule's default severity.

### Configuration and CLI

- Removing or renaming a configuration option, CLI flag, or output format.
- Making a backwards-incompatible change to how a configuration option is interpreted (for example, changing the meaning of an existing value).
- Removing a previously deprecated option or flag.
- Changing configuration discovery or precedence in a way that changes which files are read.

### Runtime

- Dropping support for an end-of-life Python version.

## What triggers a patch bump (backwards-compatible changes)

A new patch version is released for changes that should not break a passing run. This includes:

### Linter

- Adding a **new rule in [preview mode](#preview-mode)**. New rules are not enabled by default and cannot fail your build unless you opt in, so they ship in a patch release.
- Bug fixes to a rule, including cases where a rule was reporting a false positive (a fix that *removes* diagnostics is backwards-compatible; a run that passed still passes).
- Changing the behaviour of a **preview** rule in any way. Preview behaviour is explicitly unstable — see below.
- Improving diagnostic messages, help text, or documentation.

### Configuration and CLI

- Adding a new configuration option, CLI flag, or output format.
- Deprecating (but not yet removing) a configuration option or flag.

### Runtime

- Adding support for a new Python version.

## Rule stabilisation and preview mode

Following ruff, new rules do not go straight into the default rule set. Instead:

1. A new rule is first released in **preview mode**. It is off by default and only runs when you opt in (for example with a `--preview` flag or the equivalent configuration). This ships in a **patch** release.
2. A preview rule stays in preview for **at least one minor release** so that there is time to gather feedback and shake out false positives.
3. When a rule is promoted to **stable**, it may become part of the default rule set. Because this can produce new diagnostics on a previously green run, promotion happens in a **minor** release.

While a rule (or any other behaviour) is gated behind preview mode, **we reserve the right to change any of its behaviour** — including its diagnostics, its message, its severity, or removing it entirely — in a patch release. Preview exists precisely so that new checks can be refined without waiting on the stable-version cadence. If you enable preview mode, expect churn.

## Deprecation

When a rule, configuration option, or CLI flag is to be removed, it is first **deprecated** — announced in a patch release and kept working — and only **removed** in a later minor release. This gives you at least one release cycle to migrate.

## Pinning charmlint

- **In CI**, pin to an exact version (for example `charmlint==0.4.7`) and bump deliberately. This is the only way to guarantee that a new rule or a sharpened rule never turns a green build red without you choosing it.
- If you pin loosely, pin to the **patch** range (for example `~=0.4.0`, i.e. `>=0.4.0, <0.5.0`) so that you receive bug fixes and preview-gated additions but not breaking changes.

## Pre-1.0

charmlint is currently in the `0.x` series and under active development. The scheme above applies throughout `0.x`: minor (`0.x`) bumps may break you, patch (`0.x.y`) bumps should not. As with ruff, reaching `1.0.0` will not change the meaning of the minor and patch versions — it will simply signal that the tool and its default rule set have stabilised.
