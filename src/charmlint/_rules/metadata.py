"""Metadata rules — charmcraft.yaml field completeness."""

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


def _any_present(metadata: dict[str, Any], keys: tuple[str, ...]) -> bool:
    return any(_resolve(metadata, k) for k in keys)


# https://canonical.com/juju/docs/charmcraft/stable/reference/files/charmcraft-yaml-file/#charmcraft-yaml-key-name
class MissingName(Rule):
    category = "METADATA"
    number = 1
    name = "missing-name"
    description = "Missing 'name' field in charm metadata"
    default_severity = models.Severity.ERROR

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        if _resolve(context.metadata, "name"):
            return []
        return [self.diagnostic(self.description, path=context.metadata_source)]


# https://canonical.com/juju/docs/charmcraft/stable/reference/files/charmcraft-yaml-file/#charmcraft-yaml-key-title
class MissingDisplayName(Rule):
    category = "METADATA"
    number = 2
    name = "missing-display-name"
    description = "Missing 'display-name'/'title' field"
    default_severity = models.Severity.WARNING
    _keys = ("title", "display-name")

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        if _any_present(context.metadata, self._keys):
            return []
        return [self.diagnostic(self.description, path=context.metadata_source)]


# https://canonical.com/juju/docs/charmcraft/stable/reference/files/charmcraft-yaml-file/#charmcraft-yaml-key-summary
class MissingSummary(Rule):
    category = "METADATA"
    number = 3
    name = "missing-summary"
    description = "Missing 'summary' field"
    default_severity = models.Severity.ERROR

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        if _resolve(context.metadata, "summary"):
            return []
        return [self.diagnostic(self.description, path=context.metadata_source)]


# https://canonical.com/juju/docs/charmcraft/stable/reference/files/charmcraft-yaml-file/#charmcraft-yaml-key-description
class MissingDescription(Rule):
    category = "METADATA"
    number = 4
    name = "missing-description"
    description = "Missing 'description' field"
    default_severity = models.Severity.ERROR

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        if _resolve(context.metadata, "description"):
            return []
        return [self.diagnostic(self.description, path=context.metadata_source)]


# https://canonical.com/juju/docs/charmcraft/stable/reference/files/charmcraft-yaml-file/#charmcraft-yaml-key-links
class MissingDocs(Rule):
    category = "METADATA"
    number = 5
    name = "missing-docs"
    description = "Missing 'docs' URL"
    default_severity = models.Severity.INFO
    _keys = ("links.documentation", "docs")

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        if _any_present(context.metadata, self._keys):
            return []
        return [self.diagnostic(self.description, path=context.metadata_source)]


# https://canonical.com/juju/docs/charmcraft/stable/reference/files/charmcraft-yaml-file/#charmcraft-yaml-key-links-issues
class MissingIssues(Rule):
    category = "METADATA"
    number = 6
    name = "missing-issues"
    description = "Missing 'issues' URL"
    default_severity = models.Severity.INFO
    _keys = ("links.issues", "issues")

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        if _any_present(context.metadata, self._keys):
            return []
        return [self.diagnostic(self.description, path=context.metadata_source)]


# https://canonical.com/juju/docs/charmcraft/stable/reference/files/charmcraft-yaml-file/#charmcraft-yaml-key-links-source
class MissingSource(Rule):
    category = "METADATA"
    number = 7
    name = "missing-source"
    description = "Missing 'source' URL"
    default_severity = models.Severity.INFO
    _keys = ("links.source", "source")

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        if _any_present(context.metadata, self._keys):
            return []
        return [self.diagnostic(self.description, path=context.metadata_source)]
