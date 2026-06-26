"""Documentation rules — README and docs presence.

DOC001 lives here; DOC002–DOC005 return in their own PRs (after the
shared-docs-walker gating PR).
"""

from .. import _models as models
from . import Rule


class NoReadme(Rule):
    """Check for README.md presence."""

    id = "DOC001"
    name = "no-readme"
    description = "No README.md found"
    default_severity = models.Severity.WARNING

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        if not (context.charm_dir / "README.md").exists():
            return [self.diagnostic("No README.md found")]
        return []
