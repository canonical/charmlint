"""Config quality rules — types, defaults, descriptions, src/ usage.

CFG001 lives here; CFG002–CFG005 return in their own PRs.
"""

import pathlib
import re

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


class ConfigMissingDescription(Rule):
    """Check that all config options have a description."""

    id = "CFG003"
    name = "config-missing-description"
    description = "Config option is missing a description"
    default_severity = models.Severity.WARNING

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        for opt_name, opt_def in context.config_options.items():
            if not isinstance(opt_def, dict):
                continue
            if not opt_def.get("description"):
                diagnostics.append(
                    self.diagnostic(
                        f"Config option '{opt_name}' is missing a description",
                        path="charmcraft.yaml",
                    )
                )
        return diagnostics


_DYNAMIC_CONFIG_PATTERNS = [
    re.compile(r"dict\(\*\*.*?config\)"),
    re.compile(r"for\s+\w+\s+in\s+.*?config[^.\[]"),
    re.compile(r"config\.items\(\)"),
    re.compile(r"config\.values\(\)"),
]


def _option_is_read(option_name: str, sources: dict[pathlib.Path, str]) -> bool:
    """True iff some src/ source reads ``<...>.config["X"]`` or ``.config.get("X")``."""
    pattern = re.compile(rf"\bconfig(?:\[|\.get\()\s*['\"]{re.escape(option_name)}['\"]")
    for path, content in sources.items():
        if "lib" in path.parts:
            continue
        if pattern.search(content):
            return True
        for dp in _DYNAMIC_CONFIG_PATTERNS:
            if dp.search(content):
                return True
    return False


class ConfigOptionUnread(Rule):
    """Check that every declared config option is read somewhere in src/."""

    id = "CFG004"
    name = "config-option-unread"
    description = "Config option declared but never read in src/"
    default_severity = models.Severity.WARNING

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        if not context.config_options:
            return []
        diagnostics: list[models.Diagnostic] = []
        for opt_name in context.config_options:
            if _option_is_read(opt_name, context.python_sources):
                continue
            diagnostics.append(
                self.diagnostic(
                    f"Config option '{opt_name}' is declared but never read "
                    f"in src/ — operators can set it but the charm ignores it",
                    path="charmcraft.yaml",
                    fix_hint=(
                        f'Read it via `self.config["{opt_name}"]` or '
                        f'`self.config.get("{opt_name}", <default>)`'
                    ),
                )
            )
        return diagnostics


class ConfigNoBlockedStatus(Rule):
    """Flag charms with config but no BlockedStatus validation surface."""

    id = "CFG005"
    name = "config-no-blocked-status"
    description = "Charm has config options but never sets BlockedStatus"
    default_severity = models.Severity.INFO

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        if not context.config_options:
            return []
        pattern = re.compile(r"\bBlockedStatus\b")
        for path, content in context.python_sources.items():
            if "lib" in path.parts:
                continue
            if pattern.search(content):
                return []
        return [
            self.diagnostic(
                "Charm declares config options but never references "
                "BlockedStatus — invalid config has no visible status",
                fix_hint=(
                    "Validate config and set `self.unit.status = "
                    "ops.BlockedStatus('reason')` for invalid values"
                ),
            )
        ]
