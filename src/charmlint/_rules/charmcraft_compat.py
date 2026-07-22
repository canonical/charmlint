"""Charmcraft-compatible rules — checks that mirror ``charmcraft analyse``."""

import re

from .. import _models as models
from ._base import Rule


class DeprecatedSeries(Rule):
    category = "CHARMCRAFT"
    number = 1
    name = "deprecated-series"
    description = "Deprecated 'series' attribute in metadata"
    default_severity = models.Severity.WARNING
    reference_url = "https://canonical.com/juju/docs/charmcraft/stable/reference/files/charmcraft-yaml-file/#charmcraft-yaml-key-platforms"

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


class NamingConventions(Rule):
    category = "CHARMCRAFT"
    number = 2
    name = "naming-conventions"
    description = "Config option names use underscores instead of hyphens"
    default_severity = models.Severity.WARNING
    reference_url = "https://canonical.com/juju/docs/charmcraft/stable/reference/files/charmcraft-yaml-file/#charmcraft-yaml-key-config"

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        # Juju/charmcraft reject underscored action names outright, and
        # underscored action parameters are vanishingly rare in the wild,
        # so this rule targets config options only.
        diagnostics: list[models.Diagnostic] = []
        for opt_name in context.config_options:
            if "_" in opt_name:
                hyphenated = re.sub(r"[-_]+", "-", opt_name)
                diagnostics.append(
                    self.diagnostic(
                        f"Config option '{opt_name}' uses underscores — prefer hyphens ('{hyphenated}')",
                        path=context.metadata_source,
                        fix_hint=f"Rename to '{hyphenated}'",
                    )
                )
        return diagnostics
