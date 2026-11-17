"""Machine-readable output formats for CI: GitHub annotations, SARIF and JUnit.

All three name files relative to the repository root rather than to
the linted directory. Annotations and code-scanning alerts are anchored to
repository paths, so ``charmlint charms/foo`` has to report
``charms/foo/src/charm.py`` rather than ``src/charm.py``. In GitHub Actions
the root is ``$GITHUB_WORKSPACE``, which also covers a step run with a
``working-directory``. Elsewhere it's the current directory.
"""

import collections
import json
import os
import pathlib
import re

# Only ever writes XML, so the parsing attacks bandit warns about don't apply.
import xml.etree.ElementTree as ET  # ruff: ignore[suspicious-xml-etree-import]

from . import _discovery, _rules
from . import _models as models

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

# The JUnit suite and class names. Test Observer files every test case under
# the suite name as its category, so it's the same for every charm.
_JUNIT_NAME = "charmlint"

# The characters XML 1.0 allows. A message can quote a charm's own files,
# and ElementTree escapes markup but writes anything else as it is.
_XML_INVALID = re.compile("[^\t\n\r\x20-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]")


def format_github(report: models.LintReport) -> str:
    """Render *report* as GitHub Actions workflow commands, one per line.

    Each line becomes an annotation: on the PR diff when the finding has a
    file and line, and in the run summary otherwise. Unlike a SARIF result,
    a finding with no file doesn't need anchoring to the metadata file,
    because the run summary still displays it.
    """
    lines: list[str] = []
    for d in report:
        properties: list[str] = []
        if d.path is not None:
            properties.append(f"file={_escape_property(_repo_path(report.charm_dir, d.path))}")
        if d.line is not None:
            properties.append(f"line={d.line}")
        # Named, so it stands apart from other tools' annotations, such as ruff's.
        properties.append(f"title={_escape_property(f'charmlint ({d.rule_id})')}")
        command = _GITHUB_COMMANDS[d.severity]
        lines.append(f"::{command} {','.join(properties)}::{_escape_data(_full_message(d))}")
    return "\n".join(lines)


def format_sarif(report: models.LintReport) -> str:
    """Render *report* as a SARIF 2.1.0 log, for GitHub code scanning."""
    from . import __version__

    # Every rule is declared, so rule indexes don't depend on --select.
    rules = sorted(_rules.get_all_rules().values(), key=lambda r: r.id)
    rule_index = {rule.id: index for index, rule in enumerate(rules)}
    # Code scanning only displays a result that has a location, so a
    # finding about the charm as a whole is anchored to its metadata file.
    fallback = _discovery.metadata_file(report.charm_dir)

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
                "artifactLocation": {"uri": _sarif_uri(report.charm_dir, path)}
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


def format_junit(report: models.LintReport, *, strict: bool = False) -> str:
    """Render *report* as JUnit XML, with a test case per rule, for Test Observer.

    Each charm is a test suite holding a test case for every registered
    rule, so the same tests appear on every run and a rule that starts
    failing shows up as a regression. A rule's test case fails when it
    found something that fails the run: an error, or a warning with
    ``--strict``. Every finding goes in the test case's ``system-out``, which
    Test Observer keeps as the result's log. A rule that didn't run is
    skipped, and so is every rule on a charm that couldn't be loaded,
    whose ``FATAL`` test case is an error instead.
    """
    from . import __version__

    rule_ids = sorted(_rules.get_all_rules())
    root = ET.Element("testsuites", name=_JUNIT_NAME)
    for run in report.charms:
        root.append(
            _junit_suite(report.charm_dir, run, rule_ids, strict=strict, version=__version__)
        )
    _set_junit_counts(root)
    ET.indent(root)
    # ASCII, with anything else as a character reference, so the output
    # doesn't depend on the encoding of whatever it's printed to.
    return ET.tostring(root, encoding="us-ascii", xml_declaration=True).decode("ascii")


def _escape_property(value: str) -> str:
    """Escape a workflow-command property value (``file=``, ``title=``)."""
    return _escape_data(value).replace(":", "%3A").replace(",", "%2C")


def _escape_data(value: str) -> str:
    """Escape a workflow-command message, so newlines survive."""
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _repo_path(charm_dir: pathlib.Path, path: str) -> str:
    """Return *path* (relative to *charm_dir*) relative to the repository root.

    The root is ``$GITHUB_WORKSPACE`` if it's set, and the current directory
    if not. A path outside the root stays absolute, as there is no
    repository-relative form to give.
    """
    full = charm_dir / path
    # Resolved because charm_dir is, and is_relative_to doesn't follow symlinks.
    root = pathlib.Path(os.environ.get("GITHUB_WORKSPACE") or pathlib.Path.cwd()).resolve()
    if not full.is_relative_to(root):
        return full.as_posix()
    return pathlib.PurePath(os.path.relpath(full, root)).as_posix()


def _sarif_uri(charm_dir: pathlib.Path, path: str) -> str:
    """Return *path* as a SARIF URI: relative to the repository root, or else ``file://``."""
    repo_path = pathlib.Path(_repo_path(charm_dir, path))
    return repo_path.as_uri() if repo_path.is_absolute() else repo_path.as_posix()


def _full_message(d: models.Diagnostic) -> str:
    """The message, then the fix hint and reference URL as paragraphs of their own."""
    parts = [d.message]
    if d.fix_hint:
        parts.append(d.fix_hint)
    if d.reference_url:
        parts.append(f"See {d.reference_url}")
    return "\n\n".join(parts)


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


def _junit_suite(
    charm_dir: pathlib.Path,
    run: models.CharmRun,
    rule_ids: list[str],
    *,
    strict: bool,
    version: str,
) -> ET.Element:
    """Return the test suite for one charm's *run*."""
    suite = ET.Element("testsuite", name=_JUNIT_NAME)
    properties = ET.SubElement(suite, "properties")
    ET.SubElement(properties, "property", name="charmlint.version", value=version)
    ET.SubElement(properties, "property", name="charmlint.path", value=_xml_text(run.path))

    findings: dict[str, list[models.Diagnostic]] = collections.defaultdict(list)
    for d in run.diagnostics:
        findings[d.rule_id].append(d)

    # Always present, so that a charm that stops loading is a regression
    # rather than a test that disappears.
    case = _junit_case(suite, "FATAL")
    if fatal := findings.pop("FATAL", []):
        ET.SubElement(case, "error", message=_xml_text(fatal[0].message))
        _junit_output(case, charm_dir, fatal)

    # A finding from a rule that isn't registered still gets a test case.
    for rule_id in sorted({*rule_ids, *findings}):
        case = _junit_case(suite, rule_id)
        found = findings.get(rule_id, [])
        if not run.loaded:
            ET.SubElement(case, "skipped", message="the charm could not be loaded")
        elif rule_id not in run.rules_run and not found:
            ET.SubElement(case, "skipped", message="not selected")
        else:
            failing = [d for d in found if _fails_run(d, strict=strict)]
            if failing:
                worst = (
                    models.Severity.ERROR
                    if any(d.severity is models.Severity.ERROR for d in failing)
                    else models.Severity.WARNING
                )
                ET.SubElement(case, "failure", message=_count_findings(failing), type=worst)
            _junit_output(case, charm_dir, found)

    _set_junit_counts(suite)
    return suite


def _xml_text(text: str) -> str:
    """Replace the characters XML 1.0 can't hold, so the output still parses."""
    return _XML_INVALID.sub("\ufffd", text)


def _junit_case(suite: ET.Element, rule_id: str) -> ET.Element:
    """Add the test case for *rule_id* to *suite*."""
    # Test Observer looks a test up by its name alone, across every
    # product, so the name says which tool it's from.
    return ET.SubElement(suite, "testcase", classname=_JUNIT_NAME, name=f"{_JUNIT_NAME}/{rule_id}")


def _junit_output(
    case: ET.Element, charm_dir: pathlib.Path, found: list[models.Diagnostic]
) -> None:
    """Put *found* in the test case's ``system-out``, one finding to a line."""
    if found:
        output = ET.SubElement(case, "system-out")
        output.text = _xml_text("\n".join(_junit_finding(charm_dir, d) for d in found))


def _fails_run(d: models.Diagnostic, *, strict: bool) -> bool:
    """Whether *d* makes the run fail, as the exit code does."""
    return d.severity is models.Severity.ERROR or (
        strict and d.severity is models.Severity.WARNING
    )


def _count_findings(diagnostics: list[models.Diagnostic]) -> str:
    """Say how many findings of each severity there are: "1 error, 2 warnings"."""
    counts = collections.Counter(d.severity for d in diagnostics)
    return ", ".join(
        f"{counts[severity]} {severity}{'s' if counts[severity] != 1 else ''}"
        for severity in models.Severity
        if counts[severity]
    )


def _set_junit_counts(element: ET.Element) -> None:
    """Set the totals that JUnit readers expect on a suite or the whole log."""
    cases = list(element.iter("testcase"))
    element.set("tests", str(len(cases)))
    for attribute, outcome in (
        ("failures", "failure"),
        ("errors", "error"),
        ("skipped", "skipped"),
    ):
        element.set(attribute, str(sum(case.find(outcome) is not None for case in cases)))


def _junit_finding(charm_dir: pathlib.Path, d: models.Diagnostic) -> str:
    """Describe *d* on a line, with its fix hint and reference indented below."""
    location = _repo_path(charm_dir, d.path) if d.path is not None else ""
    if location and d.line is not None:
        location = f"{location}:{d.line}"
    lines = [
        f"{location}: {d.severity}: {d.message}" if location else f"{d.severity}: {d.message}"
    ]
    if d.fix_hint:
        lines.append(f"    {d.fix_hint}")
    if d.reference_url:
        lines.append(f"    See {d.reference_url}")
    return "\n".join(lines)
