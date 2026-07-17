"""Charmcraft-compatible rules — checks that mirror ``charmcraft analyse``."""

from typing import Any

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
    description = "Config options, actions, or parameters use underscores instead of hyphens"
    default_severity = models.Severity.WARNING
    reference_url = "https://canonical.com/juju/docs/ops/latest/howto/write-and-structure-charm-code/#follow-best-practices"

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        path = context.metadata_source

        for opt_name in context.config_options:
            if "_" in opt_name:
                hyphenated = opt_name.replace("_", "-")
                diagnostics.append(
                    self.diagnostic(
                        f"Config option '{opt_name}' uses underscores — prefer hyphens ('{hyphenated}')",
                        path=path,
                        fix_hint=f"Rename to '{hyphenated}'",
                    )
                )

        for action_name, action_def in context.actions.items():
            if "_" in action_name:
                hyphenated = action_name.replace("_", "-")
                diagnostics.append(
                    self.diagnostic(
                        f"Action '{action_name}' uses underscores — prefer hyphens ('{hyphenated}')",
                        path=path,
                        fix_hint=f"Rename to '{hyphenated}'",
                    )
                )
            if not isinstance(action_def, dict):
                continue
            params: Any = action_def.get("params", {})
            if not isinstance(params, dict):
                continue
            for param_name in params:
                if "_" in param_name:
                    hyphenated = param_name.replace("_", "-")
                    diagnostics.append(
                        self.diagnostic(
                            f"Action '{action_name}' parameter '{param_name}' uses underscores "
                            f"— prefer hyphens ('{hyphenated}')",
                            path=path,
                            fix_hint=f"Rename to '{hyphenated}'",
                        )
                    )

        return diagnostics
