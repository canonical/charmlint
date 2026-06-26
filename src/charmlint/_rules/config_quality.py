"""Config quality rules — types, defaults, descriptions, src/ usage.

CFG001 lives here; CFG002–CFG005 return in their own PRs.
"""

from .. import _models as models
from . import Rule


class ConfigMissingType(Rule):
    """Check that all config options have a defined type."""

    id = "CFG001"
    name = "config-missing-type"
    description = "Config option is missing a type"
    default_severity = models.Severity.WARNING

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        for opt_name, opt_def in context.config_options.items():
            if not isinstance(opt_def, dict):
                continue
            if not opt_def.get("type"):
                diagnostics.append(
                    self.diagnostic(
                        f"Config option '{opt_name}' is missing a type",
                        path="charmcraft.yaml",
                    )
                )
        return diagnostics


class ConfigMissingDefault(Rule):
    """Check that all config options have a default value."""

    id = "CFG002"
    name = "config-missing-default"
    description = "Config option is missing a default value"
    default_severity = models.Severity.INFO

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        for opt_name, opt_def in context.config_options.items():
            if not isinstance(opt_def, dict):
                continue
            if "default" not in opt_def:
                diagnostics.append(
                    self.diagnostic(
                        f"Config option '{opt_name}' is missing a default value",
                        path="charmcraft.yaml",
                    )
                )
        return diagnostics
