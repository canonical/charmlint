"""Charmcraft-compatible rules — checks that mirror ``charmcraft analyse``.

CC001 lives here; CC002–CC004 return in their own PRs.
"""

from .. import _models as models
from . import Rule


class DeprecatedSeries(Rule):
    """Detect deprecated ``series`` attribute in metadata."""

    id = "CC001"
    name = "deprecated-series"
    description = "Deprecated 'series' attribute in metadata"
    default_severity = models.Severity.WARNING

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        if "series" in context.metadata:
            return [
                self.diagnostic(
                    "'series' is deprecated in charm metadata — use 'bases' or 'platforms' instead",
                    path="charmcraft.yaml",
                    fix_hint="Remove 'series' and use 'bases' or 'platforms'",
                )
            ]
        return []
