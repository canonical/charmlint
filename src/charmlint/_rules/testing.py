"""Testing rules — test presence and framework usage."""

import re

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


class UsesHarness(Rule):
    """Detect usage of the deprecated Harness test framework."""

    id = "TEST003"
    name = "uses-harness"
    description = "Uses deprecated Harness test framework — use Scenario (ops.testing) instead"
    default_severity = models.Severity.ERROR

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        test_dir = context.charm_dir / "tests"
        if not test_dir.is_dir():
            return []

        for test_file in sorted(test_dir.rglob("*.py")):
            try:
                content = test_file.read_text(errors="replace")
            except OSError:
                continue
            if re.search(r"from\s+ops\.testing\s+import\s+Harness|Harness\s*\(", content):
                return [
                    self.diagnostic(
                        "Uses deprecated Harness — migrate to Scenario (ops.testing)",
                        path=str(test_file),
                        fix_hint="Use ops.testing.Context and State instead of Harness",
                    )
                ]
        return []


_HARNESS_IMPORT_RE = re.compile(
    r"from\s+ops\.testing\s+import\s+[^\n]*\bHarness\b|\bops\.testing\.Harness\b",
)
_CONTEXT_IMPORT_RE = re.compile(
    r"from\s+ops\.testing\s+import\s+[^\n]*\bContext\b|\bops\.testing\.Context\b",
)


class HarnessAndScenarioMixed(Rule):
    """Detect a test suite mixing both Harness and Scenario (Context)."""

    id = "TEST005"
    name = "harness-and-scenario-mixed"
    description = "Test suite uses both Harness and Scenario (Context) — pick one framework"
    default_severity = models.Severity.INFO

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        test_dir = context.charm_dir / "tests"
        if not test_dir.is_dir():
            return []

        harness_seen = False
        context_seen = False
        for test_file in sorted(test_dir.rglob("*.py")):
            try:
                content = test_file.read_text(errors="replace")
            except OSError:
                continue
            if not harness_seen and _HARNESS_IMPORT_RE.search(content):
                harness_seen = True
            if not context_seen and _CONTEXT_IMPORT_RE.search(content):
                context_seen = True
            if harness_seen and context_seen:
                break

        if harness_seen and context_seen:
            return [
                self.diagnostic(
                    "Test suite imports both Harness and Scenario (Context) — "
                    "standardise on one testing framework",
                    fix_hint=(
                        "Migrate remaining Harness tests to Scenario "
                        "(ops.testing.Context/State) and drop Harness imports"
                    ),
                )
            ]
        return []
