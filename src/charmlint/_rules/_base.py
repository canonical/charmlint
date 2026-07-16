"""Rule base class and registry.

Split from ``__init__.py`` so individual rule modules can import from
``._base`` without causing a circular import with the package init.
"""

import abc
import inspect
import re

from .. import _models as models

_RULES: dict[str, "Rule"] = {}
_CATEGORY_PATTERN = re.compile(r"^[A-Z]+$")


class Rule(abc.ABC):
    """Base class for all charmlint rules.

    Subclasses override ``category`` (uppercase word), ``number``
    (positive int), ``name``, ``description``, and ``default_severity``
    as class attributes, and implement ``check()``. The user-facing
    ``id`` is derived as ``f"{category}-{number:03d}"``. Concrete rules
    are automatically registered on class creation; abstract
    intermediates (those that leave any of the abstract members
    unimplemented) are skipped.
    """

    name: str
    description: str
    default_severity: models.Severity
    reference_url: str | None = None

    @property
    @abc.abstractmethod
    def category(self) -> str: ...

    @property
    @abc.abstractmethod
    def number(self) -> int: ...

    @property
    def id(self) -> str:
        """User-facing rule ID, e.g. ``METADATA-001``."""
        return f"{self.category}-{self.number:03d}"

    @abc.abstractmethod
    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        """Run the rule against the given charm context."""

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if inspect.isabstract(cls):
            return
        category = cls.category
        if not isinstance(category, str) or not _CATEGORY_PATTERN.match(category):
            raise ValueError(
                f"{cls.__name__}.category must be all-uppercase letters, got {category!r}"
            )
        number = cls.number
        if not isinstance(number, int) or number <= 0:
            raise ValueError(f"{cls.__name__}.number must be a positive int, got {number!r}")
        instance = cls()
        if instance.id in _RULES:
            raise ValueError(f"Duplicate rule ID: {instance.id}")
        _RULES[instance.id] = instance

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
            reference_url=self.reference_url,
        )


def get_all_rules() -> dict[str, Rule]:
    """Return a copy of the rule registry."""
    return dict(_RULES)
