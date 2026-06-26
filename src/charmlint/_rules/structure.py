"""Structure rules — charm directory structure and required files.

STR001 lives here; STR002 and STR003 return in their own PRs.
"""

from .. import _models as models
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
