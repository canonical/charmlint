"""Documentation rules — README and docs presence."""

from .. import _models as models
from ._base import Rule


class NoReadme(Rule):
    category = "DOCUMENTATION"
    number = 1
    name = "no-readme"
    description = "No README file found"
    default_severity = models.Severity.WARNING

    _extensions = frozenset({".md", ".txt", ".rst"})

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        for entry in context.charm_dir.iterdir():
            if (
                entry.is_file()
                and entry.stem.lower() == "readme"
                and entry.suffix.lower() in self._extensions
            ):
                return []
        return [self.diagnostic(self.description)]
