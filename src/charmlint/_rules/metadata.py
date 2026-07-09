"""Metadata rules — charmcraft.yaml field completeness.

Only METADATA-001 lives here during the rules-refactor; the other
METADATA rules return via their own PRs from `RULES_TRACKER.md`.
"""

from typing import Any

from .. import _models as models
from ._base import Rule


def _resolve(metadata: dict[str, Any], dotted: str) -> Any:
    cur: Any = metadata
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        if part not in cur:
            return None
        cur = cur[part]
    return cur


class MissingName(Rule):
    category = "METADATA"
    number = 1
    name = "missing-name"
    description = "Missing 'name' field in charm metadata"
    default_severity = models.Severity.ERROR

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        if _resolve(context.metadata, "name"):
            return []
        return [self.diagnostic(self.description, path=context.metadata_source)]
