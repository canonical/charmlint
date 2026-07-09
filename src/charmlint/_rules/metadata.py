"""Metadata rules — charmcraft.yaml field completeness.

Only METADATA-001 lives here during the rules-refactor; the other
METADATA rules return via their own PRs from `RULES_TRACKER.md`.
"""

from typing import Any

from .. import _models as models
from . import Rule


def _resolve(metadata: dict[str, Any], dotted: str) -> Any:
    cur: Any = metadata
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
        if cur is None:
            return None
    return cur


class MissingName(Rule):
    id = "METADATA-001"
    name = "missing-name"
    description = "Missing 'name' field in charm metadata"
    default_severity = models.Severity.ERROR

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        if _resolve(context.metadata, "name"):
            return []
        return [self.diagnostic(self.description, path=context.metadata_source)]
