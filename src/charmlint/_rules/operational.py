"""Operational readiness rules — repository hygiene for operators."""

from .. import models
from . import Rule


class NoIssueTemplate(Rule):
    """Flag charms that lack a GitHub issue template.

    A populated ``.github/ISSUE_TEMPLATE/`` directory or a single
    ``.github/ISSUE_TEMPLATE.md`` file lets operators report problems with a
    consistent shape. Without one, every issue lands as freeform prose and
    triage takes longer.
    """

    id = "OPS003"
    name = "no-issue-template"
    description = (
        "No GitHub issue template found (.github/ISSUE_TEMPLATE/ or .github/ISSUE_TEMPLATE.md)"
    )
    default_severity = models.Severity.INFO

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        github_dir = context.charm_dir / ".github"
        template_dir = github_dir / "ISSUE_TEMPLATE"
        template_file = github_dir / "ISSUE_TEMPLATE.md"
        if template_dir.is_dir() or template_file.is_file():
            return []
        return [
            self.diagnostic(
                "No GitHub issue template found — operators have no guided "
                "way to file bug reports",
                fix_hint=(
                    "Add `.github/ISSUE_TEMPLATE/bug_report.md` (or "
                    "`.github/ISSUE_TEMPLATE.md`) so issues arrive with the "
                    "information you need to triage them"
                ),
            )
        ]
