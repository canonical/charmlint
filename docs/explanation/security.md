---
myst:
  html_meta:
    description: What charmlint reads, why it never runs charm code, the risks of relying on it, and how to report a vulnerability.
---

(security)=
# Security

charmlint reads a charm's source files and reports what it finds. It runs on a developer machine or a CI runner, as the user who invokes it.

## Product architecture

charmlint is a short-lived command, not a daemon. It reads files, prints a report, then exits. Its trust boundaries follow from that position:

- charmlint doesn't trust the charm. It reads the charm's metadata files, such as `charmcraft.yaml` and `metadata.yaml`, its `pyproject.toml`, and the Python files under `src/`, `lib/`, and `tests/`. Some rules also read other files, such as `README.md`, `dispatch`, `tox.ini`, the charm's requirements files, and a `rockcraft.yaml` elsewhere in the same repository. charmlint parses these files. It never imports or runs them.
- Configuration decides which rules run. charmlint looks for a `charmlint.toml` file, a `.charmlint.toml` file, or a `[tool.charmlint]` table in `pyproject.toml`. It starts in the charm directory and walks up to the root of the file system. The `--config` option skips this search. Suppression comments in the charm's own files also silence findings.
- The report is the output. Findings go to standard output, and errors go to standard error. What happens next, such as failing a CI job on the exit code, is up to whoever runs charmlint.

charmlint opens no network connections, listens on no ports, and writes no files. It needs read access to the charm and nothing more.

## Secure by design

charmlint treats every charm as hostile input:

- It parses Python with the standard library `ast` module. Charm code, tests, and the `dispatch` script are never imported or run.
- It loads YAML with PyYAML's safe loader, which builds plain data and can't create arbitrary Python objects. It loads TOML with the standard library `tomllib` module.
- A file that can't be read or parsed becomes a `FATAL` finding in the report, rather than being skipped. A broken charm can't produce a clean report.
- When charmlint searches a directory for charms, it doesn't follow symbolic links to directories, and it goes no more than three levels deep.

charmlint has one runtime dependency, PyYAML. The charmlint CI checks charmlint's own code and dependencies:

- `ruff` lints the code, including its security rules.
- `ty` checks the types.
- `pip-audit` checks every locked dependency for known vulnerabilities.
- `zizmor` checks the GitHub workflows.

charmlint is open source, so none of its security relies on its design being secret.

## Cryptographic technology

charmlint implements and uses no cryptography.

charmlint has no data in transit, because it opens no network connections. It has no data at rest of its own, because it writes no files. The confidentiality of the charm files it reads rests on the file system permissions of the machine it runs on, and on any disk encryption you use there.

Cryptography does protect how charmlint reaches you:

- PyPI serves packages over HTTPS. Installers such as `uv` and `pip` check its certificate.
- A lock file records a hash of each package. `uv` refuses a download that doesn't match the hash in `uv.lock`.
- Each release is built and published by GitHub Actions, using PyPI's Trusted Publishing. The workflow signs build provenance and an SBOM for each file with Sigstore, as GitHub artifact attestations. PyPI also holds a signed attestation for each file.

To check that a downloaded file was built from the charmlint repository, run:

```text
gh attestation verify charmlint-0.4.0-py3-none-any.whl --repo canonical/charmlint
```

See more: [GitHub | Using artifact attestations](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations), [PyPI | Attestations](https://docs.pypi.org/attestations/)

## Configuring and operating

charmlint is safe to run with its defaults. Every rule is enabled, and charmlint needs no configuration, no credentials, and no privileges beyond read access to the charm.

### Hardening

To harden how you run charmlint:

- Pin charmlint to an exact version in CI, and update deliberately. See [Pinning charmlint](versioning.md#pinning-charmlint).
- Add charmlint to the charm's development dependencies and commit the lock file, so that the installed package must match a recorded hash. For example, `uv add --dev charmlint`.
- Pass `--config` in CI, so that a configuration file in a parent directory can't change which rules run. Add `--verbose` to print which configuration file was loaded.
- Run charmlint as an unprivileged user. It never needs `root`.
- Review new suppression comments in pull requests like any other code change. See [Suppressing findings inline](../reference/configuration.md#suppressing-findings-inline).

### Risks

These risks come with how charmlint works, and charmlint can't remove them:

- A clean report doesn't mean that a charm is secure. charmlint checks a fixed set of practices, and only in the files it reads. Use it alongside general-purpose tools, such as `ruff` and `zizmor`, and a dependency audit.
- Anyone who can change a charm's files can silence findings. A suppression comment, or a change to `[tool.charmlint]`, can hide a problem from review.
- A configuration file in any parent directory applies when the charm has none of its own. On a shared machine, another user who can write to a parent directory can change which rules run. Use `--config` to prevent this.
- charmlint follows symbolic links to files. A charm can point charmlint at a file outside the charm directory, and charmlint reads that file with your privileges. It parses the file but never runs it.
- charmlint sets no limit on the size of the files it reads. A crafted charm can make charmlint slow, or use a lot of memory. Set a timeout on the CI job that runs it.

## Logging and monitoring

charmlint doesn't log. It writes no log files, sends nothing to the system journal, and emits no security events. It has no users, sessions, or access control, so the events that a service would log, such as failed logins, don't arise.

The output of a run is its record:

- Findings go to standard output, as text or, with `--format json`, as JSON.
- The summary line goes to standard output when there are findings, and to standard error when there are none. `--quiet` drops it.
- Errors, such as an invalid path, an invalid configuration file, or an unknown rule name, go to standard error. So do the extra details that `--verbose` prints.
- The exit code says whether the run passed. See [Exit codes](../reference/cli.md#exit-codes).

To be alerted to new findings, fail the CI job on a non-zero exit code, and use the CI system's own notifications. Add `--strict` to fail on warnings too. To report fewer findings, use `--select`, `--ignore`, or `--min-severity`.

charmlint has no masking. Its output can contain absolute paths, file names, and names from the charm's files, such as configuration option names. If charmlint fails unexpectedly, Python prints a stack trace to standard error, which can contain the same details. Keep CI logs that contain charmlint output as private as the charm's source code.

## Decommissioning

charmlint stores nothing of its own. It keeps no configuration outside the charm, no cache, no logs, and no credentials.

To remove charmlint, undo the way you installed it:

- For a development dependency, run `uv remove --dev charmlint`. This also updates `uv.lock`.
- For a tool installed with `uv tool install`, run `uv tool uninstall charmlint`.
- `uvx` keeps a copy of charmlint in the `uv` cache. To remove it, run `uv cache clean charmlint`.

Then remove the charmlint configuration from the charm: the `[tool.charmlint]` table in `pyproject.toml`, any `charmlint.toml` or `.charmlint.toml` file, and any CI step that runs charmlint. Suppression comments are plain comments, so they do nothing once charmlint is gone. Remove them if you like.

charmlint output in CI logs stays until the CI system's retention period ends, or until you delete it.

## Security lifecycle

charmlint is distributed as the [`charmlint` package on PyPI](https://pypi.org/project/charmlint/), and each release has [release notes on GitHub](https://github.com/canonical/charmlint/releases). charmlint doesn't follow semantic versioning. A minor release can add or tighten rules. See [](versioning.md).

Only the latest release is supported. A release reaches end of life when the next one is published. Security fixes go into a new release, never into an earlier one. An earlier release keeps working, but without security fixes. charmlint is in the `0.x` series and has no Long Term Support releases.

To check which version you are running:

```text
charmlint --version
```

Compare the result to the latest version on PyPI.

### Receiving updates

charmlint doesn't update itself. How an update reaches you depends on how you run charmlint:

- With `uvx charmlint`, `uv` reuses the version in its cache. Run `uvx charmlint@latest` to get the latest release.
- With charmlint as a development dependency, an update reaches you when you re-lock. To apply one by hand, run `uv lock --upgrade-package charmlint`.

### Scheduling and postponing updates

To schedule updates, configure Dependabot or Renovate in the charm's repository, so that new releases arrive as pull requests. Either tool can also delay a release until it's a few days old.

Pinning charmlint to an exact version, or turning off the automated pull requests, postpones updates indefinitely. charmlint often reads code from pull requests that you haven't reviewed yet. A machine or CI runner on a version with a known vulnerability stays exposed until you update.

## Reporting vulnerabilities

If you believe you have found a security vulnerability in charmlint, please report it privately by following the instructions in [SECURITY.md](https://github.com/canonical/charmlint/blob/main/SECURITY.md).

Reports are handled according to the [Ubuntu Security disclosure and embargo policy](https://ubuntu.com/security/disclosure-policy), which describes how researchers, users, and customers can responsibly disclose issues to Canonical.

Information about known vulnerabilities affecting charmlint is published in:

- The [GitHub Security Advisories for `canonical/charmlint`](https://github.com/canonical/charmlint/security/advisories).
- The [charmlint release notes](https://github.com/canonical/charmlint/releases) on GitHub.
