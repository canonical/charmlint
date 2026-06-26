"""Testing rules — test presence and framework usage.

TEST001 lives here; TEST002 and TEST003 return in their own PRs.
"""

from .. import _models as models
from . import Rule


class NoUnitTests(Rule):
    """Check for the presence of unit tests."""

    id = "TEST001"
    name = "no-unit-tests"
    description = "No unit tests found in tests/unit/"
    default_severity = models.Severity.ERROR

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        if not context.has_tests_unit:
            return [self.diagnostic(self.description, path="tests/")]
        return []


class NoIntegrationTests(Rule):
    """Check for the presence of integration tests."""

    id = "TEST002"
    name = "no-integration-tests"
    description = "No integration tests found in tests/integration/"
    default_severity = models.Severity.WARNING

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        if not context.has_tests_integration:
            return [self.diagnostic(self.description, path="tests/")]
        return []
