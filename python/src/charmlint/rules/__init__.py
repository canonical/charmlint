"""Rule base class and registry for charmlint."""

import abc

from .. import models

# Global rule registry — populated by Rule.__init_subclass__.
_RULES: dict[str, "Rule"] = {}


class Rule(abc.ABC):
    """Base class for all charmlint rules.

    Subclasses must define ``id``, ``name``, ``description``, and
    ``default_severity`` as class attributes, and implement ``check()``.
    Rules are automatically registered on class creation.
    """

    id: str
    name: str
    description: str
    default_severity: models.Severity

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        # Only register concrete rules (those with an id attribute).
        if hasattr(cls, "id") and not getattr(cls, "_abstract", False):
            _RULES[cls.id] = cls()

    @abc.abstractmethod
    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        """Run the rule against the given charm context."""

    def diagnostic(
        self,
        message: str,
        *,
        severity: models.Severity | None = None,
        path: str | None = None,
        line: int | None = None,
        fix_hint: str | None = None,
    ) -> models.Diagnostic:
        """Convenience helper to create a Diagnostic for this rule."""
        return models.Diagnostic(
            rule_id=self.id,
            severity=severity or self.default_severity,
            message=message,
            path=path,
            line=line,
            fix_hint=fix_hint,
        )


def get_all_rules() -> dict[str, Rule]:
    """Return a copy of the rule registry."""
    return dict(_RULES)


# Import all rule modules so their Rule subclasses register on package
# import.  These imports must run after Rule and _RULES are defined; the
# rule modules `from . import Rule`, which works because Rule is already
# bound by the time the package body reaches this line.
from . import (  # noqa: E402, F401
    actions,
    attestations,
    charmcraft_compat,
    config_quality,
    deprecated,
    documentation,
    libraries,
    library_versions,
    metadata,
    observability,
    pebble,
    relation_data,
    security,
    status,
    structure,
    testing,
    unknown_fields,
)
