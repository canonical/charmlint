"""Supply chain rules — dependency pinning and provenance."""

from .. import models
from . import Rule

_DEPENDENCY_UPDATE_CONFIGS = (
    ".github/dependabot.yml",
    ".github/dependabot.yaml",
    "renovate.json",
    ".github/renovate.json",
    ".renovaterc",
    ".renovaterc.json",
)


class NoDependencyUpdates(Rule):
    """Check that the charm configures automated dependency updates."""

    id = "SUPP002"
    name = "no-dependency-updates"
    description = "No automated dependency update configuration found"
    default_severity = models.Severity.INFO

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        for candidate in _DEPENDENCY_UPDATE_CONFIGS:
            if (context.charm_dir / candidate).exists():
                return []
        return [
            self.diagnostic(
                "No automated dependency update configuration found "
                "(.github/dependabot.yml or renovate.json) — without "
                "automation, dependencies drift and security fixes lag",
                fix_hint=(
                    "Add .github/dependabot.yml or renovate.json so that "
                    "dependency bumps are proposed automatically"
                ),
            )
        ]
