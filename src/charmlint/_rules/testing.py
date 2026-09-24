"""Testing rules — test presence and framework usage."""

import ast

from .. import _ast
from .. import _models as models
from ._base import Rule


class NoUnitTests(Rule):
    """Check for the presence of unit tests."""

    category = "TESTING"
    number = 1
    name = "no-unit-tests"
    description = "No unit tests found in tests/unit/ or unit_tests/"
    default_severity = models.Severity.WARNING
    example = {
        "charmcraft.yaml": """
            name: web-frontend
            type: charm
        """,
    }
    fix = {
        "tests/unit/test_charm.py": """
            import ops.testing

            from charm import WebFrontendCharm


            def test_pebble_ready_starts_service():
                ctx = ops.testing.Context(WebFrontendCharm)
                container = ops.testing.Container("frontend", can_connect=True)
                state_in = ops.testing.State(containers={container})
                state_out = ctx.run(ctx.on.pebble_ready(container), state_in)
                assert state_out.unit_status == ops.ActiveStatus()
        """,
    }

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        # has_tests_unit is populated by _linter._check_tests.
        if not context.has_tests_unit:
            return [self.diagnostic(self.description, path="tests/unit/")]
        return []


class UsesHarness(Rule):
    """Detect unit tests written against the deprecated ``Harness``.

    ``tests/unit/`` and the rest of the test tree are examined, but not
    ``tests/integration/``: a charm with a flat ``tests/`` keeps its unit
    tests at the top level, and shared fixtures live in
    ``tests/conftest.py`` whichever layout is used. Integration tests
    drive a real deployment rather than either testing API, and a
    vendored library's own tests are its author's problem.

    One finding per test module, anchored at the first mention, rather
    than one per ``Harness(...)`` call: a suite that uses Harness uses it
    everywhere, and the migration is per-file work.
    """

    category = "TESTING"
    number = 3
    name = "uses-harness"
    description = "Unit tests use the deprecated ops.testing.Harness"
    default_severity = models.Severity.WARNING
    reference_url = (
        "https://canonical.com/juju/docs/ops/latest/howto/migrate/migrate-unit-tests-from-harness/"
    )
    example = {
        "charmcraft.yaml": """
            name: web-frontend
            type: charm
        """,
        "tests/unit/test_charm.py": """
            from ops.testing import Harness

            from charm import WebFrontendCharm


            def test_pebble_ready_starts_service():
                harness = Harness(WebFrontendCharm)
                harness.begin_with_initial_hooks()
                harness.container_pebble_ready("frontend")
                assert harness.model.unit.status.name == "active"
        """,
    }
    fix = {
        "tests/unit/test_charm.py": """
            import ops
            from ops import testing

            from charm import WebFrontendCharm


            def test_pebble_ready_starts_service():
                ctx = testing.Context(WebFrontendCharm)
                container = testing.Container("frontend", can_connect=True)
                state_in = testing.State(containers={container})
                state_out = ctx.run(ctx.on.pebble_ready(container), state_in)
                assert state_out.unit_status == ops.ActiveStatus()
        """,
    }

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        for module in context.modules(models.Scope.TESTS_UNIT, models.Scope.TESTS_OTHER):
            line = _harness_line(module)
            if line is None:
                continue
            diagnostics.append(
                self.diagnostic(
                    "Unit tests use ops.testing.Harness, which is deprecated "
                    "— use the ops.testing state-transition API instead",
                    path=module.path,
                    line=line,
                    fix_hint="Rewrite the test with ops.testing.Context and ops.testing.State",
                )
            )
        return diagnostics


# The deprecated class, spelled canonically. Every spelling a charm might
# use — ``ops.testing.Harness``, ``from ops.testing import Harness``,
# ``from ops import testing`` then ``testing.Harness`` — resolves to this
# through the module's import table, so the rule matches meaning rather
# than text.
_HARNESS = "ops.testing.Harness"


def _harness_line(module: models.Module) -> int | None:
    """Return the first line of *module* that refers to ``Harness``.

    ``None`` when the module does not use it. Both name chains and bare
    names are resolved through the import table, so a local class that
    happens to be called ``Harness`` does not match: without an import
    binding the name, it resolves to itself.
    """
    imports = _ast.Imports.of(module)
    lines = [
        node.lineno
        for node in module.walk(ast.Name, ast.Attribute)
        if imports.resolve(node) == _HARNESS
    ]
    return min(lines) if lines else None
