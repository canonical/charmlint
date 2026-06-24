"""JUJU rules — Juju-ness / idiomatic ops conventions."""

import re

from .. import models
from . import Rule

# A charm "uses Juju secrets" if any of these appear in src/ (not lib/).
_USES_SECRETS_RE = re.compile(
    r"\.add_secret\s*\(|\.get_secret\s*\(|\bSecret\.get_content\s*\(",
)

# Either of these observers satisfies the rotation/expiry handling expectation.
_OBSERVES_ROTATE_RE = re.compile(r"observe\(\s*self\.on\.secret_rotate\b")
_OBSERVES_EXPIRED_RE = re.compile(r"observe\(\s*self\.on\.secret_expired\b")


class NoSecretRotateHandler(Rule):
    """Flag charms that use Juju secrets but don't observe rotation/expiry."""

    id = "JUJU008"
    name = "no-secret-rotate-handler"
    description = (
        "Charm uses Juju secrets but does not observe `secret_rotate` or `secret_expired`"
    )
    default_severity = models.Severity.WARNING

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        # Concatenate src/ sources only (skip vendored lib/ charm libraries).
        src_source = "\n".join(
            content for path, content in context.python_sources.items() if "lib" not in path.parts
        )
        if not src_source:
            return []
        if not _USES_SECRETS_RE.search(src_source):
            return []
        if _OBSERVES_ROTATE_RE.search(src_source) or _OBSERVES_EXPIRED_RE.search(src_source):
            return []
        return [
            self.diagnostic(
                "Charm uses Juju secrets but does not observe `secret_rotate` "
                "or `secret_expired` — rotation/expiry events will be missed",
                fix_hint=(
                    "Observe `self.on.secret_rotate` (and/or `self.on.secret_expired`) "
                    "and refresh the secret content in the handler"
                ),
            )
        ]
