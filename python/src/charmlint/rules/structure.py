"""Structure rules — charm directory structure and required files."""

import re

from .. import models
from . import Rule


class NoLicence(Rule):
    """Check for a licence file."""

    id = "STR001"
    name = "no-licence"
    description = "No LICENSE/LICENCE file found"
    default_severity = models.Severity.INFO

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        has_licence = (context.charm_dir / "LICENSE").exists() or (
            context.charm_dir / "LICENCE"
        ).exists()
        if not has_licence:
            return [self.diagnostic("No LICENSE/LICENCE file found")]
        return []


class NoIcon(Rule):
    """Check for an icon file."""

    id = "STR002"
    name = "no-icon"
    description = "No icon.svg found"
    default_severity = models.Severity.INFO

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        if not (context.charm_dir / "icon.svg").exists():
            return [self.diagnostic("No icon.svg found")]
        return []


class NoTypeAnnotations(Rule):
    """Check that charm source uses type annotations."""

    id = "STR003"
    name = "no-type-annotations"
    description = "No type annotations found in charm source"
    default_severity = models.Severity.INFO

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        for path, content in context.python_sources.items():
            # Only check src/ files (skip lib/).
            if "lib" in path.parts:
                continue
            if re.search(r"def\s+\w+\([^)]*\)\s*->", content):
                return []
        return [
            self.diagnostic(
                "No type annotations found — add return-type hints to functions",
                fix_hint="Add -> ReturnType annotations to function definitions",
            )
        ]
