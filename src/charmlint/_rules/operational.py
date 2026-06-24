"""Operational readiness rules — repository hygiene for operators."""

from typing import Any

from .. import models
from . import Rule


class DescriptionMissingRelations(Rule):
    """Flag charms whose description does not mention required relations.

    Operators reading the description should see, in prose, the relations
    they need to wire up. If a required (non-optional) ``requires:`` endpoint
    name (or its hyphen-replaced-with-space form) is missing from the
    description text, this rule fires.

    Speculative / high false-positive — info severity, fires only when none
    of the required relation names appear at all.
    """

    id = "OPS004"
    name = "description-missing-relations"
    description = "Charm description does not mention any required relation"
    default_severity = models.Severity.INFO

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        description = context.metadata.get("description")
        if not isinstance(description, str) or not description.strip():
            return []

        requires = context.metadata.get("requires")
        if not isinstance(requires, dict):
            return []

        required_names = _required_relation_names(requires)
        if not required_names:
            return []

        haystack = description.lower()
        for name in required_names:
            if name in haystack or name.replace("-", " ") in haystack:
                return []

        joined = ", ".join(sorted(required_names))
        return [
            self.diagnostic(
                (
                    "Charm description does not mention any required relation "
                    f"({joined}) — operators may not realise they need to wire these up"
                ),
                path="charmcraft.yaml",
                fix_hint=(
                    "Mention each required relation by name in the description "
                    "so operators know which integrations are mandatory"
                ),
            )
        ]


def _required_relation_names(requires: dict[str, Any]) -> list[str]:
    """Return lowercased names of non-optional ``requires:`` endpoints."""
    names: list[str] = []
    for name, rel_def in requires.items():
        if not isinstance(name, str):
            continue
        if isinstance(rel_def, dict) and rel_def.get("optional") is True:
            continue
        names.append(name.lower())
    return names
