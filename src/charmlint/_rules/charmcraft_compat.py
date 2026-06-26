"""Charmcraft-compatible rules — checks that mirror ``charmcraft analyse``.

CC001–CC003 live here; CC004 returns in its own PR.
"""

import os
import re
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


class Entrypoint(Rule):
    """Check that the charm entrypoint exists and is executable."""

    id = "CC003"
    name = "entrypoint-issues"
    description = "Charm entrypoint missing or not executable"
    default_severity = models.Severity.ERROR

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        dispatch = context.charm_dir / "dispatch"
        if not dispatch.exists():
            return []

        try:
            content = dispatch.read_text(errors="replace")
        except OSError:
            return []

        match = re.search(r"(?:exec\s+)?[./]*(\S+\.py)", content)
        if not match:
            return []

        entrypoint_rel = match.group(1)
        entrypoint = context.charm_dir / entrypoint_rel

        diagnostics: list[models.Diagnostic] = []
        if not entrypoint.exists():
            diagnostics.append(
                self.diagnostic(
                    f"Entrypoint '{entrypoint_rel}' referenced in dispatch does not exist",
                    path="dispatch",
                )
            )
        elif not entrypoint.is_file():
            diagnostics.append(
                self.diagnostic(
                    f"Entrypoint '{entrypoint_rel}' is not a regular file",
                    path="dispatch",
                )
            )
        elif not os.access(entrypoint, os.X_OK):
            diagnostics.append(
                self.diagnostic(
                    f"Entrypoint '{entrypoint_rel}' is not executable",
                    path=str(entrypoint_rel),
                    fix_hint=f"Run: chmod +x {entrypoint_rel}",
                )
            )

        return diagnostics
