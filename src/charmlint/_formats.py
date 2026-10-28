"""Machine-readable output formats for CI: GitHub annotations and SARIF.

Both formats name files relative to the current directory rather than to
the linted directory. In GitHub Actions the current directory is the
repository checkout, and annotations and code-scanning alerts are anchored
to repository paths, so ``charmlint charms/foo`` has to report
``charms/foo/src/charm.py`` rather than ``src/charm.py``.
"""

import json
import os
import pathlib

from . import _models as models
from . import _rules

_GITHUB_COMMANDS: dict[models.Severity, str] = {
    models.Severity.ERROR: "error",
    models.Severity.WARNING: "warning",
    models.Severity.INFO: "notice",
}

_SARIF_LEVELS: dict[models.Severity, str] = {
    models.Severity.ERROR: "error",
    models.Severity.WARNING: "warning",
    models.Severity.INFO: "note",
}

_SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
_INFORMATION_URI = "https://github.com/canonical/charmlint"


def format_github(report: models.LintReport) -> str:
    """Render *report* as GitHub Actions workflow commands, one per line.

    Each line becomes an annotation: on the PR diff when the finding has a
    file and line, and in the run summary otherwise.
    """
    lines: list[str] = []
    for d in report:
        properties: list[str] = []
        if d.path is not None:
            properties.append(f"file={_escape_property(_repo_path(report.charm_dir, d.path))}")
        if d.line is not None:
            properties.append(f"line={d.line}")
        properties.append(f"title={_escape_property(d.rule_id)}")
        command = _GITHUB_COMMANDS[d.severity]
        lines.append(f"::{command} {','.join(properties)}::{_escape_data(_full_message(d))}")
    return "\n".join(lines)


def format_sarif(report: models.LintReport) -> str:
    """Render *report* as a SARIF 2.1.0 log, for GitHub code scanning."""
    from . import __version__

    rules = sorted(_rules.get_all_rules().values(), key=lambda r: r.id)
    rule_index = {rule.id: index for index, rule in enumerate(rules)}
    # Code scanning only displays a result that has a location, so a
    # finding about the charm as a whole is anchored to its metadata file.
    fallback = _fallback_path(report.charm_dir)

    results: list[dict[str, object]] = []
    for d in report:
        result: dict[str, object] = {
            "ruleId": d.rule_id,
            "level": _SARIF_LEVELS[d.severity],
            "message": {"text": _full_message(d)},
        }
        if d.rule_id in rule_index:
            result["ruleIndex"] = rule_index[d.rule_id]
        path = d.path if d.path is not None else fallback
        if path is not None:
            physical: dict[str, object] = {
                "artifactLocation": {
                    "uri": _repo_path(report.charm_dir, path),
                    "uriBaseId": "%SRCROOT%",
                }
            }
            if d.path is not None and d.line is not None:
                physical["region"] = {"startLine": d.line}
            result["locations"] = [{"physicalLocation": physical}]
        results.append(result)

    log = {
        "$schema": _SARIF_SCHEMA,
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "charmlint",
                        "version": __version__,
                        "informationUri": _INFORMATION_URI,
                        "rules": [_sarif_rule(rule) for rule in rules],
                    }
                },
                "results": results,
            }
        ],
    }
    return json.dumps(log, indent=2)


def _escape_property(value: str) -> str:
    """Escape a workflow-command property value (``file=``, ``title=``)."""
    return _escape_data(value).replace(":", "%3A").replace(",", "%2C")


def _escape_data(value: str) -> str:
    """Escape a workflow-command message, so newlines survive."""
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _repo_path(charm_dir: pathlib.Path, path: str) -> str:
    """Return *path* (relative to *charm_dir*) relative to the current directory.

    A path outside the current directory stays absolute, as there is no
    repository-relative form to give.
    """
    full = charm_dir / path
    cwd = pathlib.Path.cwd()
    if not full.is_relative_to(cwd):
        return full.as_posix()
    return pathlib.PurePath(os.path.relpath(full, cwd)).as_posix()


def _full_message(d: models.Diagnostic) -> str:
    """The message, followed by the fix hint and reference URL when there are any."""
    parts = [d.message]
    if d.fix_hint:
        parts.append(f"Fix: {d.fix_hint}")
    if d.reference_url:
        parts.append(f"See {d.reference_url}")
    return "\n".join(parts)


def _fallback_path(charm_dir: pathlib.Path) -> str | None:
    """The linted directory's metadata file, to anchor findings that have no file."""
    for name in ("charmcraft.yaml", "metadata.yaml"):
        if (charm_dir / name).is_file():
            return name
    return None


def _sarif_rule(rule: _rules.Rule) -> dict[str, object]:
    """Describe *rule* as a SARIF ``reportingDescriptor``."""
    help_text = rule.description
    if rule.reference_url:
        help_text = f"{help_text}\n\nSee {rule.reference_url}"
    descriptor: dict[str, object] = {
        "id": rule.id,
        "name": rule.name,
        "shortDescription": {"text": rule.description},
        "fullDescription": {"text": rule.description},
        "help": {"text": help_text},
        "defaultConfiguration": {"level": _SARIF_LEVELS[rule.default_severity]},
        "properties": {"tags": [rule.category.lower()]},
    }
    if rule.reference_url:
        descriptor["helpUri"] = rule.reference_url
    return descriptor
