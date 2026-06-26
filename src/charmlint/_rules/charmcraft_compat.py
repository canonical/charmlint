"""Charmcraft-compatible rules — checks that mirror ``charmcraft analyse``.

CC001–CC002 live here; CC003–CC004 return in their own PRs.
"""

from typing import Any

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


class NamingConventions(Rule):
    """Check that config options, actions, and parameters use hyphenated names."""

    id = "CC002"
    name = "naming-conventions"
    description = "Config options, actions, or parameters use underscores instead of hyphens"
    default_severity = models.Severity.WARNING

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []

        for opt_name in context.config_options:
            if "_" in opt_name:
                diagnostics.append(
                    self.diagnostic(
                        f"Config option '{opt_name}' uses underscores "
                        f"— prefer hyphens ('{opt_name.replace('_', '-')}')",
                        path="charmcraft.yaml",
                    )
                )

        for action_name, action_def in context.actions.items():
            if "_" in action_name:
                diagnostics.append(
                    self.diagnostic(
                        f"Action '{action_name}' uses underscores "
                        f"— prefer hyphens ('{action_name.replace('_', '-')}')",
                        path="charmcraft.yaml",
                    )
                )
            if not isinstance(action_def, dict):
                continue
            params: dict[str, Any] = action_def.get("params", action_def.get("parameters", {}))
            if not isinstance(params, dict):
                continue
            properties = params.get("properties", params)
            for param_name in properties:
                if "_" in param_name:
                    diagnostics.append(
                        self.diagnostic(
                            f"Action '{action_name}' parameter '{param_name}' uses underscores "
                            f"— prefer hyphens ('{param_name.replace('_', '-')}')",
                            path="charmcraft.yaml",
                        )
                    )

        return diagnostics
