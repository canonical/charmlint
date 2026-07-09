"""Metadata rules — charmcraft.yaml / metadata.yaml field completeness.

Each rule checks the key spelling that belongs in the file the charm
actually uses: modern charmcraft.yaml uses `title` and `links.*`; legacy
metadata.yaml uses `display-name`, `docs`, `issues`, `source` at top
level. Accepting the wrong spelling in the wrong file would silently
paper over a real misplacement.
"""

from typing import Any

from .. import _models as models
from ._base import Rule


def _resolve(metadata: dict[str, Any], dotted: str) -> Any:
    cur: Any = metadata
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        if part not in cur:
            return None
        cur = cur[part]
    return cur


def _is_charmcraft(context: models.CharmContext) -> bool:
    return context.metadata_source == "charmcraft.yaml"


def _is_bundle(context: models.CharmContext) -> bool:
    # Bundles declare `type: bundle` in charmcraft.yaml, or use the legacy
    # top-level bundle.yaml layout. Neither shape needs the charm-metadata
    # fields these rules check for.
    if context.metadata.get("type") == "bundle":
        return True
    return (context.charm_dir / "bundle.yaml").is_file()


# https://canonical.com/juju/docs/charmcraft/stable/reference/files/charmcraft-yaml-file/#charmcraft-yaml-key-name
class MissingName(Rule):
    category = "METADATA"
    number = 1
    name = "missing-name"
    description = "Empty or missing 'name' field in charm metadata"
    default_severity = models.Severity.ERROR

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        if _is_bundle(context):
            return []
        if _resolve(context.metadata, "name"):
            return []
        return [self.diagnostic(self.description, path=context.metadata_source)]


# https://canonical.com/juju/docs/charmcraft/stable/reference/files/charmcraft-yaml-file/#charmcraft-yaml-key-title
class MissingDisplayName(Rule):
    category = "METADATA"
    number = 2
    name = "missing-display-name"
    description = "Empty or missing 'display-name'/'title' field"
    default_severity = models.Severity.WARNING

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        if _is_bundle(context):
            return []
        key = "title" if _is_charmcraft(context) else "display-name"
        if _resolve(context.metadata, key):
            return []
        return [self.diagnostic(f"Empty or missing '{key}' field", path=context.metadata_source)]


# https://canonical.com/juju/docs/charmcraft/stable/reference/files/charmcraft-yaml-file/#charmcraft-yaml-key-summary
class MissingSummary(Rule):
    category = "METADATA"
    number = 3
    name = "missing-summary"
    description = "Empty or missing 'summary' field"
    default_severity = models.Severity.ERROR

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        if _is_bundle(context):
            return []
        if _resolve(context.metadata, "summary"):
            return []
        return [self.diagnostic(self.description, path=context.metadata_source)]


# https://canonical.com/juju/docs/charmcraft/stable/reference/files/charmcraft-yaml-file/#charmcraft-yaml-key-description
class MissingDescription(Rule):
    category = "METADATA"
    number = 4
    name = "missing-description"
    description = "Empty or missing 'description' field"
    default_severity = models.Severity.ERROR

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        if _is_bundle(context):
            return []
        if _resolve(context.metadata, "description"):
            return []
        return [self.diagnostic(self.description, path=context.metadata_source)]


# https://canonical.com/juju/docs/charmcraft/stable/reference/files/charmcraft-yaml-file/#charmcraft-yaml-key-links
class MissingDocs(Rule):
    category = "METADATA"
    number = 5
    name = "missing-docs"
    description = "Empty or missing 'docs' URL"
    default_severity = models.Severity.INFO

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        if _is_bundle(context):
            return []
        key = "links.documentation" if _is_charmcraft(context) else "docs"
        if _resolve(context.metadata, key):
            return []
        return [self.diagnostic(f"Empty or missing '{key}' URL", path=context.metadata_source)]


# https://canonical.com/juju/docs/charmcraft/stable/reference/files/charmcraft-yaml-file/#charmcraft-yaml-key-links-issues
class MissingIssues(Rule):
    category = "METADATA"
    number = 6
    name = "missing-issues"
    description = "Empty or missing 'issues' URL"
    default_severity = models.Severity.INFO

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        if _is_bundle(context):
            return []
        key = "links.issues" if _is_charmcraft(context) else "issues"
        if _resolve(context.metadata, key):
            return []
        return [self.diagnostic(f"Empty or missing '{key}' URL", path=context.metadata_source)]


# https://canonical.com/juju/docs/charmcraft/stable/reference/files/charmcraft-yaml-file/#charmcraft-yaml-key-links-source
class MissingSource(Rule):
    category = "METADATA"
    number = 7
    name = "missing-source"
    description = "Empty or missing 'source' URL"
    default_severity = models.Severity.INFO

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        if _is_bundle(context):
            return []
        key = "links.source" if _is_charmcraft(context) else "source"
        if _resolve(context.metadata, key):
            return []
        return [self.diagnostic(f"Empty or missing '{key}' URL", path=context.metadata_source)]
