"""Structure rules — charm directory structure and required files."""

import pathlib

from .. import _models as models
from ._base import Rule


def _is_valid_licence(path: pathlib.Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


class NoLicence(Rule):
    """Check that the charm ships a licence file.

    Charm source is published for people to read, fork and fix, and
    without a licence file none of them know on what terms they may.

    ``LICENSE`` and ``LICENCE`` are both accepted, but only at the
    charm root and only spelled in upper case — a ``COPYING``, a
    ``LICENSE.txt``, or a licence kept under ``docs/`` is not
    recognised. An empty file is not a licence either. Shipping *both*
    spellings is reported in its own right: two files invite the two
    drifting apart, and leave a reader guessing which one governs.
    """

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


class NoIcon(Rule):
    """Check that the charm ships an ``icon.svg``.

    The icon is how the charm is recognised on Charmhub; a charm
    without one is shown under a placeholder, alongside every other
    charm that skipped it.

    The file has to be at the charm root, named exactly ``icon.svg``,
    and non-empty — a zero-byte placeholder is reported as though it
    were missing. Nothing inside the SVG is examined: dimensions and
    viewBox are charmcraft's business, not this rule's.
    """

    category = "STRUCTURE"
    number = 2
    name = "no-icon"
    description = "No icon.svg found"
    default_severity = models.Severity.INFO
    reference_url = (
        "https://canonical.com/juju/docs/charmcraft/stable/reference/files/icon-svg-file/"
    )

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        icon = context.charm_dir / "icon.svg"
        if not icon.is_file() or icon.stat().st_size == 0:
            return [self.diagnostic(self.description)]
        return []
