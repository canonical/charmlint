"""Testing rules — test presence and framework usage."""

from .. import _models as models
from ._base import Rule


class NoUnitTests(Rule):
    """Check for the presence of unit tests."""

    category = "TESTING"
    number = 1
    name = "no-unit-tests"
    description = "No unit tests found in tests/unit/ or unit_tests/"
    default_severity = models.Severity.WARNING

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        # has_tests_unit is populated by _linter._check_tests.
        if not context.has_tests_unit:
            return [self.diagnostic(self.description, path="tests/unit/")]
        return []
