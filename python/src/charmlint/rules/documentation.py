"""Documentation rules — README and docs presence."""

from .. import models
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


class MissingInstallationDocs(Rule):
    """Check for installation documentation."""

    id = "DOC002"
    name = "missing-installation-docs"
    description = "No installation/setup documentation found"
    default_severity = models.Severity.WARNING

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        return _check_doc_topic(self, context, "installation", "installation/setup")


class MissingConfigurationDocs(Rule):
    """Check for configuration documentation."""

    id = "DOC003"
    name = "missing-configuration-docs"
    description = "No configuration documentation found"
    default_severity = models.Severity.INFO

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        return _check_doc_topic(self, context, "configuration", "configuration")


class MissingUsageDocs(Rule):
    """Check for usage documentation."""

    id = "DOC004"
    name = "missing-usage-docs"
    description = "No usage documentation found"
    default_severity = models.Severity.INFO

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        return _check_doc_topic(self, context, "usage", "usage")


class MissingTroubleshootingDocs(Rule):
    """Check for troubleshooting documentation."""

    id = "DOC005"
    name = "missing-troubleshooting-docs"
    description = "No troubleshooting documentation found"
    default_severity = models.Severity.INFO

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        return _check_doc_topic(self, context, "troubleshooting", "troubleshooting")


def _check_doc_topic(
    rule: Rule,
    context: models.CharmContext,
    keyword: str,
    label: str,
) -> list[models.Diagnostic]:
    """Check if a documentation topic is present in README or docs/."""
    # Check README.
    if keyword in context.readme_content.lower():
        return []

    # Check the charm's own docs/, then walk up to a repo root (looking for
    # .git) so monorepo charms that share a top-level docs/ tree aren't
    # flagged for every topic.
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


def _candidate_docs_dirs(charm_dir):
    """Yield docs/ candidates: the charm dir, then ancestor dirs up to a repo root."""
    seen = set()
    current = charm_dir.resolve()
    yield current / "docs"
    seen.add(current)
    # Walk up until we hit the filesystem root or a .git marker (inclusive).
    for parent in current.parents:
        if parent in seen:
            break
        seen.add(parent)
        yield parent / "docs"
        if (parent / ".git").exists():
            break
