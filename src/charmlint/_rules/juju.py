"""JUJU rules — Juju-ness / idiomatic ops conventions."""

from .. import _models as models
from ._base import Rule


def _missing_optional_diagnostics(
    rule: Rule,
    endpoints: object,
    section: str,
    metadata_source: str,
) -> list[models.Diagnostic]:
    """Return one diagnostic per endpoint in ``section`` lacking ``optional``."""
    if not isinstance(endpoints, dict) or not endpoints:
        return []
    diagnostics: list[models.Diagnostic] = []
    for name, definition in endpoints.items():
        if not isinstance(definition, dict):
            continue
        if "optional" in definition:
            continue
        diagnostics.append(
            rule.diagnostic(
                f"{section} endpoint `{name}` does not declare `optional` — "
                "charm authors should explicitly state whether the relation is "
                "required for the charm to function",
                path=metadata_source,
                fix_hint=(
                    f"Add `optional: true` or `optional: false` to the `{name}` "
                    f"entry under `{section}`"
                ),
            )
        )
    return diagnostics


class RequiresMissingOptional(Rule):
    """Flag ``requires`` endpoints that don't explicitly declare ``optional``."""

    category = "JUJU"
    number = 1
    name = "requires-missing-optional"
    description = "requires endpoint missing explicit `optional` field"
    default_severity = models.Severity.INFO
    reference_url = "https://canonical.com/juju/docs/charmcraft/4.3/reference/files/charmcraft-yaml-file/#endpoint-role-endpoint-name-optional"

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        return _missing_optional_diagnostics(
            self, context.metadata.get("requires"), "requires", context.metadata_source
        )


class ProvidesMissingOptional(Rule):
    """Flag ``provides`` endpoints that don't explicitly declare ``optional``."""

    category = "JUJU"
    number = 2
    name = "provides-missing-optional"
    description = "provides endpoint missing explicit `optional` field"
    default_severity = models.Severity.INFO
    reference_url = "https://canonical.com/juju/docs/charmcraft/4.3/reference/files/charmcraft-yaml-file/#endpoint-role-endpoint-name-optional"

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        return _missing_optional_diagnostics(
            self, context.metadata.get("provides"), "provides", context.metadata_source
        )
