"""Structure rules — charm directory structure and required files."""

from .. import _models as models
from ._base import Rule


class NoLicence(Rule):
    category = "STRUCTURE"
    number = 1
    name = "no-licence"
    description = "No LICENSE/LICENCE file found"
    default_severity = models.Severity.INFO

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        if (context.charm_dir / "LICENSE").exists() or (context.charm_dir / "LICENCE").exists():
            return []
        return [self.diagnostic(self.description)]
