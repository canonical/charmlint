"""Supply chain rules — dependency pinning and provenance."""

from .. import models
from . import Rule


class NoLockfile(Rule):
    """Check that the charm has a dependency lockfile."""

    id = "SUPP001"
    name = "no-lockfile"
    description = "No uv.lock or poetry.lock found"
    default_severity = models.Severity.WARNING

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        has_lockfile = (context.charm_dir / "uv.lock").exists() or (
            context.charm_dir / "poetry.lock"
        ).exists()
        if not has_lockfile:
            return [
                self.diagnostic(
                    "No uv.lock or poetry.lock found — unpinned transitive "
                    "dependencies make builds non-reproducible and expose "
                    "the charm to supply-chain drift",
                    fix_hint=(
                        "Commit a lockfile (run `uv lock` or `poetry lock`) "
                        "so dependency versions are pinned and auditable"
                    ),
                )
            ]
        return []
