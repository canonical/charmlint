"""Deprecated API detection rules."""

import pathlib
import re

from .. import models
from . import Rule

# (regex_pattern, rule_id, name, message, fix_hint)
_DEPRECATED_CHECKS: list[tuple[str, str, str, str, str]] = [
    (
        r"\bStoredState\b",
        "DEP001",
        "uses-stored-state",
        "Uses deprecated StoredState",
        "Use instance attributes or Juju secrets instead",
    ),
    (
        r"\bfrom\s+ops\.testing\s+import\s+Harness\b",
        "DEP002",
        "uses-harness-import",
        "Imports deprecated Harness from ops.testing",
        "Use Scenario (ops.testing.Context, State) instead",
    ),
    (
        r"\bself\.framework\.breakpoint\b",
        "DEP003",
        "uses-framework-breakpoint",
        "Uses removed framework.breakpoint()",
        "Use standard Python breakpoint() or debugger",
    ),
    (
        r"from\s+charms\.reactive\b|@(?:when|when_not|when_any|when_all|hook)\(",
        "DEP004",
        "uses-reactive-framework",
        "Uses legacy reactive framework (charms.reactive / @when / @hook decorators)",
        "Rewrite as an ops.CharmBase subclass with framework.observe() event handlers",
    ),
]


def _find_first_match(
    pattern: str, sources: dict[pathlib.Path, str]
) -> tuple[pathlib.Path, int] | None:
    """Find the first file and line matching a pattern."""
    compiled = re.compile(pattern)
    for path, content in sources.items():
        # Only check src/ files for deprecated APIs (skip lib/).
        if "lib" in path.parts:
            continue
        for i, line in enumerate(content.splitlines(), 1):
            if compiled.search(line):
                return path, i
    return None


def _make_deprecated_rule(
    _pattern: str,
    _id: str,
    _name: str,
    _message: str,
    _fix: str,
) -> type[Rule]:
    """Dynamically create a Rule subclass for a deprecated API check."""
    # Bind to local names so the class body can reference them.
    pat, rid, rname, msg, hint = _pattern, _id, _name, _message, _fix

    class _DeprecatedRule(Rule):
        id = rid
        name = rname
        description = msg
        default_severity = models.Severity.ERROR

        def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
            match = _find_first_match(pat, context.python_sources)
            if match:
                fpath, line = match
                return [self.diagnostic(msg, path=str(fpath), line=line, fix_hint=hint)]
            return []

    _DeprecatedRule.__name__ = f"DeprecatedRule_{rid}"
    _DeprecatedRule.__qualname__ = _DeprecatedRule.__name__
    return _DeprecatedRule


for _pattern, _rule_id, _name, _message, _fix_hint in _DEPRECATED_CHECKS:
    _make_deprecated_rule(_pattern, _rule_id, _name, _message, _fix_hint)
