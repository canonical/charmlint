---
myst:
  html_meta:
    description: Learn how to run charmlint on a charm, read its findings, fix one, and configure which rules run.
---

# Getting started with charmlint

In this tutorial, we'll run charmlint on a small charm, read what it reports, and fix one of the findings. Then we'll choose which rules run, and suppress a finding that we don't want to fix.

The tutorial assumes that you know what a charm is and are comfortable in a terminal. You don't need Juju or Charmcraft, because charmlint only reads the charm's source files.

## Install uv

charmlint is published to PyPI, and the quickest way to run it is with [uv](https://docs.astral.sh/uv/). If you don't have uv, [install it](https://docs.astral.sh/uv/getting-started/installation/) first.

charmlint requires Python 3.12 or later. uv downloads a suitable Python if your system doesn't have one.

## Create a charm

You'd usually start a charm with `charmcraft init`. That creates more files than we need here, so we'll write a tiny charm by hand instead. Create a directory for the charm:

```text
$ mkdir -p my-charm/src
$ cd my-charm
```

Create `charmcraft.yaml` with this content:

```yaml
name: my-charm
type: charm
title: My Charm
summary: A tiny charm for trying out charmlint.
description: |
  A tiny charm that doesn't do anything useful. It's for trying out charmlint.

base: ubuntu@24.04
platforms:
  amd64:

parts:
  charm:
    plugin: uv
    source: .
    build-snaps:
      - astral-uv

config:
  options:
    admin-password:
      type: string
      description: The password for the workload's admin user.
    external-hostname:
      type: string
      description: The hostname to use in links to the workload. If unset, the charm uses the unit's address.
```

Create `pyproject.toml`:

```toml
[project]
name = "my-charm"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["ops>=3"]
```

And create `src/charm.py`:

```python
#!/usr/bin/env python3
"""A tiny charm for trying out charmlint."""

import ops


class MyCharm(ops.CharmBase):
    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        framework.observe(self.on.start, self._on_start)

    def _on_start(self, event: ops.StartEvent):
        self.unit.status = ops.ActiveStatus()


if __name__ == "__main__":
    ops.main(MyCharm)
```

## Run charmlint

In the `my-charm` directory, run charmlint:

```text
$ uvx charmlint
charmcraft.yaml:21 SECURITY-001 Config option 'admin-password' looks like a secret — use Juju secrets instead of plain-text config
DOCUMENTATION-001 No README file found
tests/unit/ TESTING-001 No unit tests found in tests/unit/ or unit_tests/
charmcraft.yaml:21 CONFIG-002 Config option 'admin-password' is missing a default value
charmcraft.yaml:24 CONFIG-002 Config option 'external-hostname' is missing a default value
charmcraft.yaml FEATURES-004 No `assumes:` entry declaring a minimum Juju version — Juju cannot refuse to deploy the charm onto a controller too old for it
charmcraft.yaml FEATURES-005 Charm never calls `set_workload_version()` — the workload version column in `juju status` stays empty
charmcraft.yaml METADATA-005 Empty or missing 'links.documentation' URL
charmcraft.yaml METADATA-006 Empty or missing 'links.issues' URL
charmcraft.yaml METADATA-007 Empty or missing 'links.source' URL
STRUCTURE-001 No LICENSE/LICENCE file found
STRUCTURE-002 No icon.svg found

Found 12 issues (1 error, 2 warnings, 9 info)
```

charmlint lints the current directory by default. To lint a charm somewhere else, pass its path, such as `uvx charmlint path/to/charm`.

Each line is one finding. A finding starts with where the problem is: a file, and a line number if there is one. Next is the ID of the rule that found it, such as `SECURITY-001`, then a message. Some findings, such as the missing README, have no location.

The last line counts the findings by severity. There's one error, two warnings, and nine findings at the `info` severity. Because there's an error, charmlint exits with code 1:

```text
$ echo $?
1
```

That's what makes a CI job fail. Warnings and info findings don't change the exit code.

## Fix a finding

The error is `SECURITY-001`: a config option that looks like a password. Config values are visible to anyone who can read the model's configuration. A password belongs in a Juju secret instead.

In `charmcraft.yaml`, change the type of `admin-password` from `string` to `secret`:

```yaml
    admin-password:
      type: secret
      description: The password for the workload's admin user.
```

With this type, the option holds the ID of a Juju user secret rather than the password itself. Run charmlint again:

```text
$ uvx charmlint
DOCUMENTATION-001 No README file found
tests/unit/ TESTING-001 No unit tests found in tests/unit/ or unit_tests/
charmcraft.yaml:24 CONFIG-002 Config option 'external-hostname' is missing a default value
charmcraft.yaml FEATURES-004 No `assumes:` entry declaring a minimum Juju version — Juju cannot refuse to deploy the charm onto a controller too old for it
charmcraft.yaml FEATURES-005 Charm never calls `set_workload_version()` — the workload version column in `juju status` stays empty
charmcraft.yaml METADATA-005 Empty or missing 'links.documentation' URL
charmcraft.yaml METADATA-006 Empty or missing 'links.issues' URL
charmcraft.yaml METADATA-007 Empty or missing 'links.source' URL
STRUCTURE-001 No LICENSE/LICENCE file found
STRUCTURE-002 No icon.svg found

Found 10 issues (2 warnings, 8 info)
```

The error is gone, and so is the `CONFIG-002` finding about `admin-password`. A secret option doesn't need a default. charmlint now exits with code 0.

## Choose which rules run

charmlint reads its configuration from a `[tool.charmlint]` table in the charm's `pyproject.toml`. Let's look at only the configuration and security rules for now. Add this to the end of `pyproject.toml`:

```toml
[tool.charmlint]
select = ["CONFIG", "SECURITY"]
```

`CONFIG` and `SECURITY` are categories. Each one selects every rule in that category. Run charmlint again:

```text
$ uvx charmlint
charmcraft.yaml:24 CONFIG-002 Config option 'external-hostname' is missing a default value

Found 1 issue (1 info)
```

Only the configuration and security rules ran, and one finding is left.

## Suppress a finding

`CONFIG-002` suggests a default for `external-hostname`. But this option has no default on purpose: when it's unset, the charm uses the unit's address. We'll suppress the finding with a comment, so that the reason sits next to the option.

In `charmcraft.yaml`, add a comment on the line above `external-hostname`:

```yaml
    # charmlint: ignore[config-missing-default]  # Unset means "use the unit's address".
    external-hostname:
      type: string
      description: The hostname to use in links to the workload. If unset, the charm uses the unit's address.
```

`config-missing-default` is the name of rule `CONFIG-002`. Wherever charmlint accepts a rule, you can use its ID or its name. Run charmlint again:

```text
$ uvx charmlint
No issues found.
```

## Ignore rules

`select` is useful for focusing on a few rules. Usually, though, you'll want every rule except the ones that don't suit your charm. Let's say we'll design an icon later, and our workload has no version to report. In `pyproject.toml`, replace the `select` line with an `ignore` line:

```toml
[tool.charmlint]
ignore = ["no-icon", "FEATURES-005"]
```

Run charmlint again:

```text
$ uvx charmlint
DOCUMENTATION-001 No README file found
tests/unit/ TESTING-001 No unit tests found in tests/unit/ or unit_tests/
charmcraft.yaml FEATURES-004 No `assumes:` entry declaring a minimum Juju version — Juju cannot refuse to deploy the charm onto a controller too old for it
charmcraft.yaml METADATA-005 Empty or missing 'links.documentation' URL
charmcraft.yaml METADATA-006 Empty or missing 'links.issues' URL
charmcraft.yaml METADATA-007 Empty or missing 'links.source' URL
STRUCTURE-001 No LICENSE/LICENCE file found

Found 7 issues (2 warnings, 5 info)
```

Every rule ran except the two we ignored. The rest of the findings are a to-do list for a real charm: a README, unit tests, a licence, and links to the charm's documentation, issues, and source.

## Next steps

You've now learned the basics of charmlint! To learn more:

- Look up what each rule checks for in [Rules](../reference/rules).
- See [Configuration](../reference/configuration) for the other settings and the other ways to suppress findings.
- See [Command-line interface](../reference/cli) for the command-line options and exit codes.
- Read [Versioning](../explanation/versioning) before you pin charmlint in CI.

If you have any problems or want to request new features, please [open an issue](https://github.com/canonical/charmlint/issues/new).
