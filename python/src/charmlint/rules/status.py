"""Status reporting rules — charm sets appropriate status for conditions."""

import re

from .. import models
from . import Rule

# Each check: (condition_pattern, rule_id, name, message)
_STATUS_CHECKS: list[tuple[str, str, str, str]] = [
    (
        r"missing.*config|config.*missing|no.*config",
        "STS001",
        "no-blocked-for-missing-config",
        "No BlockedStatus for missing required configuration",
    ),
    (
        r"conflict.*config|invalid.*config|config.*invalid",
        "STS002",
        "no-blocked-for-invalid-config",
        "No BlockedStatus for conflicting/invalid configuration",
    ),
    (
        r"missing.*relation|relation.*missing|no.*relation",
        "STS003",
        "no-status-for-missing-relations",
        "No status set for missing relations",
    ),
]


def _src_content(context: models.CharmContext) -> str:
    """Concatenate all src/ Python source (not lib/)."""
    parts: list[str] = []
    for path, content in context.python_sources.items():
        if "lib" not in path.parts:
            parts.append(content)
    return "\n".join(parts)


def _make_status_rule(_pat: str, _id: str, _name: str, _msg: str) -> type[Rule]:
    """Create a Rule subclass for a status reporting check."""
    pat, rid, rname, msg = _pat, _id, _name, _msg

    class _StatusRule(Rule):
        id = rid
        name = rname
        description = msg
        default_severity = models.Severity.WARNING

        def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
            source = _src_content(context)
            if not source:
                return []

            has_status_call = bool(re.search(r"(?:Blocked|Waiting|Maintenance)Status", source))
            has_condition = bool(re.search(pat, source, re.IGNORECASE))

            if not (has_condition and has_status_call):
                return [self.diagnostic(msg)]
            return []

    _StatusRule.__name__ = f"StatusRule_{rid}"
    _StatusRule.__qualname__ = _StatusRule.__name__
    return _StatusRule


for _pattern, _rule_id, _name, _message in _STATUS_CHECKS:
    _make_status_rule(_pattern, _rule_id, _name, _message)
