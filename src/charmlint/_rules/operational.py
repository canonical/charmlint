"""Operational readiness rules — repository hygiene for operators."""

import re

from .. import models
from . import Rule

# Substring pattern (case-insensitive) for action names that expose diagnostic
# information operators can collect when something goes wrong.
_DIAG_ACTION_PATTERN = re.compile(r"debug|diag|log|dump|status", re.IGNORECASE)


class NoDebugAction(Rule):
    """Flag long-lived workload charms that lack a diagnostic action.

    Charms that run a long-lived service (declared via ``containers:`` in
    metadata, or a ``packages:`` block) should expose an action operators
    can run to collect logs or status when triaging a problem.  Without
    one, operators have to ``juju ssh`` and rummage by hand.

    Any action whose name contains ``debug``, ``diag``, ``log``, ``dump``,
    or ``status`` (case-insensitive) satisfies the rule.
    """

    id = "OPS001"
    name = "no-debug-action"
    description = "Long-lived workload charm has no diagnostic / get-debug-log action"
    default_severity = models.Severity.INFO

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        metadata = context.metadata
        has_containers = bool(metadata.get("containers"))
        has_packages = bool(metadata.get("packages"))
        if not (has_containers or has_packages):
            return []
        if any(_DIAG_ACTION_PATTERN.search(name) for name in context.actions):
            return []
        return [
            self.diagnostic(
                "Long-lived workload charm has no diagnostic action — "
                "operators have no built-in way to collect logs or status",
                fix_hint=(
                    "Add an action such as `get-debug-log` (or one whose name "
                    "contains debug/diag/log/dump/status) that gathers and "
                    "returns workload diagnostics"
                ),
            )
        ]
