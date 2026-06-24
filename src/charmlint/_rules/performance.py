"""Performance rules — runtime cost issues in charm source."""

import ast

from .. import models
from . import Rule


def _is_time_sleep(call: ast.Call) -> bool:
    """True if ``call`` is a ``time.sleep(...)`` invocation."""
    func = call.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "sleep"
        and isinstance(func.value, ast.Name)
        and func.value.id == "time"
    )


class TimeSleepInHook(Rule):
    """Flag ``time.sleep(...)`` calls in charm source.

    The Juju hook runner has a wall-clock timeout; sleeping burns that
    budget, delays other hooks, and is almost always a sign of polling
    for a condition better handled by ``event.defer()`` or a Pebble
    notice.
    """

    id = "PERF001"
    name = "time-sleep-in-hook"
    description = "time.sleep() called in charm source"
    default_severity = models.Severity.WARNING

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        for path, content in context.python_sources.items():
            if "lib" in path.parts:
                continue
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not (isinstance(node, ast.Call) and _is_time_sleep(node)):
                    continue
                diagnostics.append(
                    self.diagnostic(
                        "time.sleep() called in charm source — sleeping burns the "
                        "Juju hook wall-clock budget and blocks other hooks",
                        path=str(path),
                        line=node.lineno,
                        fix_hint=(
                            "Use event.defer() to retry on the next event, or a "
                            "Pebble notice to react to workload readiness"
                        ),
                    )
                )
        return diagnostics
