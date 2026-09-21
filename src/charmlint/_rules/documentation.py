"""Documentation rules — README and docs presence."""

from .. import _models as models
from ._base import Rule


class NoReadme(Rule):
    """Check that the charm has a README.

    The README is what someone landing in the repository reads first,
    and for many charms it is the only documentation there is.

    ``README`` with a ``.md``, ``.txt`` or ``.rst`` extension satisfies
    the rule, in any case combination, and it has to sit at the charm
    root: a README one directory down documents that directory, not the
    charm. An extensionless ``README`` is reported, since nothing
    renders it.
    """

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
