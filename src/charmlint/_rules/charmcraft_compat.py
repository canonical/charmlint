"""Charmcraft-compatible rules — checks that mirror ``charmcraft analyse``.

CHARMCRAFT-001 lives here; the remaining CHARMCRAFT rules return via
their own PRs — see ``RULES_TRACKER.md``.
"""

from .. import _models as models
from ._base import Rule


class DeprecatedSeries(Rule):
    category = "CHARMCRAFT"
    number = 1
    name = "deprecated-series"
    description = "Deprecated 'series' attribute in metadata"
    default_severity = models.Severity.WARNING

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        if "series" not in context.metadata:
            return []
        return [
            self.diagnostic(
                "'series' is deprecated in charm metadata — use 'bases' or 'platforms' instead",
                path=context.metadata_source,
                fix_hint="Remove 'series' and use 'bases' or 'platforms'",
            )
        ]
