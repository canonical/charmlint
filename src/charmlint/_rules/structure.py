"""Structure rules — charm directory structure and required files."""

import pathlib

from .. import _models as models
from ._base import Rule


def _is_valid_licence(path: pathlib.Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


class NoLicence(Rule):
    category = "STRUCTURE"
    number = 1
    name = "no-licence"
    description = "No LICENSE/LICENCE file found"
    default_severity = models.Severity.INFO

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        # LICENSE (US) and LICENCE (UK) are both accepted.
        valid = [
            name for name in ("LICENSE", "LICENCE") if _is_valid_licence(context.charm_dir / name)
        ]
        if not valid:
            return [self.diagnostic(self.description)]
        if len(valid) == 2:
            return [self.diagnostic("Both LICENSE and LICENCE files present; keep only one.")]
        return []
