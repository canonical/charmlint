"""Metadata rules — charmcraft.yaml field completeness."""

from typing import Any

from .. import models
from . import Rule

# (rule_id, human_description, default_severity, accepted_keys)
# Each accepted_keys is a tuple of dotted paths into the metadata mapping.
# The check passes if *any* path resolves to a truthy value, so modern
# charmcraft.yaml (title, links.{documentation,issues,source}) and legacy
# metadata.yaml (display-name, docs, issues, source) both satisfy the rule.
_METADATA_CHECKS: list[tuple[str, str, str, models.Severity, tuple[str, ...]]] = [
    ("name", "META001", "Missing 'name' field in charm metadata", models.Severity.ERROR, ("name",)),
    (
        "display-name",
        "META002",
        "Missing 'display-name'/'title' field",
        models.Severity.WARNING,
        ("title", "display-name"),
    ),
    ("summary", "META003", "Missing 'summary' field", models.Severity.WARNING, ("summary",)),
    (
        "description",
        "META004",
        "Missing 'description' field",
        models.Severity.WARNING,
        ("description",),
    ),
    (
        "docs",
        "META005",
        "Missing 'docs' URL",
        models.Severity.INFO,
        ("links.documentation", "docs"),
    ),
    (
        "issues",
        "META006",
        "Missing 'issues' URL",
        models.Severity.INFO,
        ("links.issues", "issues"),
    ),
    (
        "source",
        "META007",
        "Missing 'source' URL",
        models.Severity.INFO,
        ("links.source", "source"),
    ),
]


def _resolve(metadata: dict[str, Any], dotted: str) -> Any:
    cur: Any = metadata
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
        if cur is None:
            return None
    return cur


def _make_rule(
    _field: str, _id: str, _msg: str, _sev: models.Severity, _keys: tuple[str, ...]
) -> type[Rule]:
    """Dynamically create a Rule subclass for a metadata field check."""
    fld, rid, msg, sev, keys = _field, _id, _msg, _sev, _keys

    class _MetadataRule(Rule):
        id = rid
        name = f"missing-{fld}"
        description = msg
        default_severity = sev

        def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
            for key in keys:
                value = _resolve(context.metadata, key)
                if value:
                    return []
            return [self.diagnostic(msg, path="charmcraft.yaml")]

    _MetadataRule.__name__ = f"MetadataRule_{rid}"
    _MetadataRule.__qualname__ = _MetadataRule.__name__
    return _MetadataRule


# Register all metadata rules.
for _field, _rule_id, _message, _severity, _accepted in _METADATA_CHECKS:
    _make_rule(_field, _rule_id, _message, _severity, _accepted)
