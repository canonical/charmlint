# Versioning

charmlint uses a versioning scheme modelled on [ruff's](https://docs.astral.sh/ruff/versioning/). If you are familiar with ruff, charmlint's version numbers should behave the way you expect: the **minor** version number is used for breaking changes and the **patch** version number is used for bug fixes.

This is *not* [SemVer](https://semver.org). The version is `major.minor.patch`, and each part means:

| Part | Bumped for |
|---|---|
| major | A large, deliberate overhaul of charmlint. Major versions don't come on a regular cadence. |
| minor | A [breaking change](#what-triggers-a-minor-bump-breaking-changes). |
| patch | A [bug fix or other backwards-compatible change](#what-triggers-a-patch-bump-backwards-compatible-changes). |

Because the minor version carries breaking changes, a bump from, say, `0.4.7` to `0.5.0` may require action on your part, while `0.4.7` to `0.4.8` should always be safe.

## Why not SemVer?

A linter is unusual: almost every improvement is, strictly speaking, a breaking change. Adding a rule, or teaching an existing rule to catch a new case, can surface diagnostics that were not reported before, which can fail a CI run that was previously green. Under strict SemVer, charmlint could barely publish anything without a major version bump, which would make the major version meaningless.

Instead, as ruff does, we reserve the *minor* version for changes that are likely to break you, and the *patch* version for everything else. Ruff softens this further with a preview mode that lets new rules land in patch releases. charmlint doesn't have a [preview mode](#preview-mode) yet.

## What triggers a minor bump (breaking changes)

A new minor version is released when charmlint makes a change that is likely to require action from you. This includes:

### Linter

- Adding a new rule. Every new rule is enabled by default, so every new rule is a breaking change. Once there's a [preview mode](#preview-mode), this applies only to promoting a rule from preview to stable.
- Changing the behaviour of a rule so that it reports diagnostics it didn't before, or stops reporting ones it did. For example, broadening what a rule considers a violation.
- Removing a rule from the set of rules enabled by default.
- Removing a rule, or deprecating a rule and removing it in the same release.
- Changing a rule's default severity.

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

- Bug fixes to a rule, including cases where a rule was reporting a false positive. A fix that *removes* diagnostics is backwards-compatible, because a run that passed still passes.
- Improving diagnostic messages, help text, or documentation.
- Once [preview mode](#preview-mode) exists: adding a new rule in preview, and changing the behaviour of a preview rule in any way.

### Configuration and CLI

- Adding a new configuration option, CLI flag, or output format.
- Deprecating (but not yet removing) a configuration option or flag.

### Runtime

- Adding support for a new Python version.

## Preview mode

charmlint doesn't have a preview mode yet. Every rule that ships is enabled by default, which is why adding a rule is a minor (breaking) release. We expect to add one, following ruff's model. This section describes how versioning is intended to work once it exists.

Under that model, new rules would not go straight into the default rule set. Instead:

1. A new rule is first released in **preview mode**. It is off by default and only runs when you opt in (for example with a `--preview` flag or the equivalent configuration). This ships in a **patch** release.
2. A preview rule stays in preview until we're confident in it, typically **at least a month**, so that there is time to gather feedback and shake out false positives.
3. When a rule is promoted to **stable**, it may become part of the default rule set. Because this can produce new diagnostics on a previously green run, promotion happens in a **minor** release.

While a rule, or any other behaviour, is gated behind preview mode, **we reserve the right to change any of its behaviour** in a patch release. That includes its diagnostics, its message and its severity, and removing it entirely. Preview exists precisely so that new checks can be refined without waiting on the stable-version cadence. If you enable preview mode, expect churn.

Preview mode also affects how a rule can be named. `select`, `ignore`, `per-rule-severity` and the codes in a suppression comment reject a token that names nothing charmlint knows about, and a preview rule is something charmlint knows about even when it is not running. Naming a preview rule while preview is off should therefore be an error that says so, and names `--preview`, rather than the generic "not a known rule ID" or a silent no-op.

Introducing preview mode is itself a minor release, since it changes how new rules reach the default rule set, and this page changes with it.

## Deprecation

When a rule, configuration option, or CLI flag is to be removed, it's first **deprecated**: announced in a patch release and kept working. It's only **removed** in a later minor release. This gives you at least one release cycle to migrate.

## Pinning charmlint

- **In CI**, pin to an exact version (for example `charmlint==0.4.7`) and bump deliberately. This is the only way to guarantee that a new rule or a sharpened rule never turns a green build red without you choosing it.
- If you pin loosely, pin to the **patch** range (for example `~=0.4.0`, which is `>=0.4.0, <0.5.0`) so that you receive bug fixes but not breaking changes.

## Pre-1.0

charmlint is in the `0.x` series and under active development. This scheme applies throughout `0.x`. Minor (`0.x`) bumps may break you, and patch (`0.x.y`) bumps should not. As with ruff, reaching `1.0.0` won't change the meaning of the minor and patch versions. It signals that the tool and its default rule set have stabilised.
