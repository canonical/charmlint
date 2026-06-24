"""Supply chain rules — dependency pinning and provenance."""

from .. import models
from . import Rule


class NoCIWorkflow(Rule):
    """Check that the charm has a GitHub Actions CI/CD workflow."""

    id = "SUPP004"
    name = "no-ci-workflow"
    description = "No .github/workflows/ directory or it contains no workflow files"
    default_severity = models.Severity.WARNING

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        workflows_dir = context.charm_dir / ".github" / "workflows"
        if workflows_dir.is_dir():
            has_workflow = any(p.suffix in (".yml", ".yaml") for p in workflows_dir.iterdir())
            if has_workflow:
                return []
        return [
            self.diagnostic(
                "No .github/workflows/ directory (or it contains no workflow "
                "files) — without CI, PRs are merged without automated lint, "
                "unit tests, or pack/analyse checks",
                fix_hint=(
                    "Add a GitHub Actions workflow under .github/workflows/ "
                    "that runs lint, unit tests, and `charmcraft pack` on PRs"
                ),
            )
        ]
