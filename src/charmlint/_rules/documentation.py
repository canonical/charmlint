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


# Shared helpers for DOC002–DOC005 — landed ahead of those rules.


def _candidate_docs_dirs(charm_dir):
    """Yield docs/ candidates: only the charm's own docs/ directory."""
    yield charm_dir.resolve() / "docs"


def _check_doc_topic(
    rule: Rule,
    context: models.CharmContext,
    keyword: str,
    label: str,
) -> list[models.Diagnostic]:
    """Check if a documentation topic is present in README or docs/."""
    if keyword in context.readme_content.lower():
        return []

    for docs_dir in _candidate_docs_dirs(context.charm_dir):
        if not docs_dir.is_dir():
            continue
        for doc_file in docs_dir.rglob("*.md"):
            try:
                content = doc_file.read_text(errors="replace").lower()
                if keyword in content:
                    return []
            except OSError:
                continue

    return [rule.diagnostic(f"No {label} documentation found")]
