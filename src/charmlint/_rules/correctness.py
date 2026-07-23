"""Correctness rules — runtime-correctness issues in charm source."""

import ast

from .. import _models as models
from ._base import Rule


class ExecResultNotConsumed(Rule):
    """Flag bare ``container.exec(...)`` calls whose result is discarded.

    A bare ``container.exec(...)`` starts the process but never waits for it,
    never captures its exit code, and can stall the container if stdout or
    stderr fills the pipe buffer. The result must either be assigned (so the
    caller can ``.wait()`` / ``.wait_output()`` later) or chained directly,
    e.g. ``container.exec(...).wait_output()``.
    """

    category = "CORRECTNESS"
    number = 3
    name = "exec-result-not-consumed"
    description = "container.exec() result not consumed (no .wait() / .wait_output())"
    default_severity = models.Severity.ERROR

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        for path, content in context.python_sources.items():
            # Library code (lib/) is vendored from elsewhere; only lint the
            # charm's own src/.
            if "lib" in path.parts:
                continue
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue
            rel = str(path.relative_to(context.charm_dir))
            for node in ast.walk(tree):
                # Only bare expression statements are problematic. A chained
                # ``.wait()`` parses as ``Call(func=Attribute(attr='wait',
                # value=Call(attr='exec', ...)))`` — the outer Expr.value is
                # the wait call, not the exec call — so matching attr='exec'
                # on Expr.value naturally skips chained calls.
                if not isinstance(node, ast.Expr):
                    continue
                call = node.value
                if not (
                    isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Attribute)
                    and call.func.attr == "exec"
                ):
                    continue
                diagnostics.append(
                    self.diagnostic(
                        "container.exec() result not consumed — the process runs "
                        "asynchronously, no exit code is checked, and a full "
                        "stdout/stderr buffer can stall the container",
                        path=rel,
                        line=call.lineno,
                        fix_hint=(
                            "Chain `.wait()` or `.wait_output()` on the call, "
                            "or assign the result and call `.wait*()` on it later"
                        ),
                    )
                )
        return diagnostics
