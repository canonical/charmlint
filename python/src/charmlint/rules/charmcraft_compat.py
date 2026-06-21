"""Charmcraft-compatible rules — checks that mirror ``charmcraft analyse``.

These rules catch issues that charmcraft analyse would find in a packed
charm, but run pre-pack on the source tree so developers get faster
feedback.
"""

import os
import re
from typing import Any

from .. import models
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
    """Check that config options, actions, and parameters use hyphenated names.

    Juju conventions use hyphens (``my-option``) not underscores
    (``my_option``) for config options, actions, and action parameters.
    """

    id = "CC002"
    name = "naming-conventions"
    description = "Config options, actions, or parameters use underscores instead of hyphens"
    default_severity = models.Severity.WARNING

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []

        # Check config option names.
        for opt_name in context.config_options:
            if "_" in opt_name:
                diagnostics.append(
                    self.diagnostic(
                        f"Config option '{opt_name}' uses underscores "
                        f"— prefer hyphens ('{opt_name.replace('_', '-')}')",
                        path="charmcraft.yaml",
                    )
                )

        # Check action names and parameter names.
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
            # No dispatch file — not applicable (could be a reactive charm).
            return []

        # Parse the dispatch file to find the entrypoint.
        try:
            content = dispatch.read_text(errors="replace")
        except OSError:
            return []

        # Look for a Python file reference in dispatch.
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


class OpsMainCall(Rule):
    """Check that an ops-framework charm calls ``ops.main()`` in its entrypoint."""

    id = "CC004"
    name = "no-ops-main-call"
    description = "Charm entrypoint does not call ops.main()"
    default_severity = models.Severity.WARNING

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        # Only applies to charms that import ops.
        has_ops = False
        entrypoint_content = ""
        for path, content in context.python_sources.items():
            if "lib" in path.parts:
                continue
            if re.search(r"\bimport\s+ops\b|from\s+ops\b", content):
                has_ops = True
                entrypoint_content += content + "\n"

        if not has_ops:
            return []

        # Check for ops.main() call.
        if re.search(r"ops\.main\s*\(|main\s*\(\s*\w+Charm\s*\)", entrypoint_content):
            return []

        return [
            self.diagnostic(
                "Charm source imports ops but does not call ops.main()",
                fix_hint="Add ops.main(MyCharm) at the end of the entrypoint",
            )
        ]
