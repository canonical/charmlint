"""Testing rules — test presence and framework usage."""

import ast
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


def _is_context_call(call: ast.Call) -> bool:
    """True if ``call`` looks like a ``testing.Context(...)`` invocation."""
    func = call.func
    if isinstance(func, ast.Attribute) and func.attr == "Context":
        return True
    return isinstance(func, ast.Name) and func.id == "Context"


class ContextLegacyKwargs(Rule):
    """Flag ``testing.Context(...)`` calls passing Harness-era ``meta``/``config`` kwargs."""

    id = "TEST006"
    name = "testing-context-legacy-kwargs"
    description = "testing.Context() called with Harness-era meta= or config= keyword arguments"
    default_severity = models.Severity.WARNING

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        test_dir = context.charm_dir / "tests"
        if not test_dir.is_dir():
            return []

        diagnostics: list[models.Diagnostic] = []
        for test_file in sorted(test_dir.rglob("*.py")):
            try:
                content = test_file.read_text(errors="replace")
            except OSError:
                continue
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not (isinstance(node, ast.Call) and _is_context_call(node)):
                    continue
                bad = next(
                    (kw.arg for kw in node.keywords if kw.arg in ("meta", "config")),
                    None,
                )
                if bad is None:
                    continue
                diagnostics.append(
                    self.diagnostic(
                        f"testing.Context() called with legacy `{bad}=` kwarg — "
                        "Scenario reads metadata/config from the charm project",
                        path=str(test_file),
                        line=node.lineno,
                        fix_hint=(
                            "Drop `meta=`/`config=`; Scenario loads charmcraft.yaml "
                            "(and metadata.yaml/config.yaml) from the charm directory"
                        ),
                    )
                )
        return diagnostics
