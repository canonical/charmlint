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


class WhileSleepPolling(Rule):
    """Flag ``while`` loops whose body contains ``time.sleep(...)``.

    A ``while`` + ``time.sleep`` polling loop in a hook burns the Juju
    hook wall-clock budget, blocks other hooks, and is almost always
    better expressed by deferring the event or reacting to a Pebble
    notice.
    """

    id = "PERF002"
    name = "while-sleep-polling"
    description = "while loop containing time.sleep() in charm source"
    default_severity = models.Severity.ERROR

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
                if not isinstance(node, ast.While):
                    continue
                if not any(isinstance(d, ast.Call) and _is_time_sleep(d) for d in ast.walk(node)):
                    continue
                diagnostics.append(
                    self.diagnostic(
                        "while loop with time.sleep() in charm source — "
                        "polling burns the Juju hook wall-clock budget and "
                        "blocks other hooks",
                        path=str(path),
                        line=node.lineno,
                        fix_hint=(
                            "Replace the polling loop with event.defer() to "
                            "retry on the next event, or a Pebble notice to "
                            "react to workload readiness"
                        ),
                    )
                )
        return diagnostics
