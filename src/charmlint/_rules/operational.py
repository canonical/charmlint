"""Operational readiness rules — repository hygiene for operators."""

import re

from .. import models
from . import Rule

# Substring pattern (case-insensitive) for action names that let operators
# nudge a misbehaving workload back to life without bouncing the unit.
_RESTART_ACTION_PATTERN = re.compile(r"restart|replan|reload|force", re.IGNORECASE)


class NoRestartAction(Rule):
    """Flag container workload charms that expose no restart-style action.

    Charms that run a workload in a Pebble-managed container (declared via
    ``containers:`` in metadata) should expose an action operators can run
    to restart, replan, reload, or otherwise force the workload back into
    a good state. Without one, operators have to remove and redeploy the
    unit to recover from a stuck service.

    Any action whose name contains ``restart``, ``replan``, ``reload``,
    or ``force`` (case-insensitive) satisfies the rule.
    """

    id = "OPS002"
    name = "no-restart-action"
    description = "Container workload charm has no restart / replan / reload / force action"
    default_severity = models.Severity.INFO

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        if not context.metadata.get("containers"):
            return []
        if any(_RESTART_ACTION_PATTERN.search(name) for name in context.actions):
            return []
        return [
            self.diagnostic(
                "Container workload charm has no restart-style action — "
                "operators have no built-in way to force the workload back "
                "into a good state",
                fix_hint=(
                    "Add an action such as `restart` (or one whose name "
                    "contains restart/replan/reload/force) that bounces "
                    "the workload via Pebble"
                ),
            )
        ]
