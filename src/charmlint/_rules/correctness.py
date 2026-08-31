"""Correctness rules — runtime-correctness issues in charm source."""

import ast

from .. import _ast as ast_
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
        for module in context.charm_sources():
            for node in module.walk(ast.Expr):
                # Only bare expression statements are problematic. A chained
                # ``.wait()`` parses as ``Call(func=Attribute(attr='wait',
                # value=Call(attr='exec', ...)))`` — the outer Expr.value is
                # the wait call, not the exec call — so matching on the
                # statement's own call naturally skips chained calls.
                call = node.value
                if not isinstance(call, ast.Call):
                    continue
                target = ast_.call_target(call)
                if target is None or not target.endswith(".exec"):
                    continue
                # Only ops.Container.exec() (Pebble) is non-blocking and needs a
                # trailing .wait*(). Charms conventionally name that receiver
                # ``container`` (e.g. ``container``, ``self.container``,
                # ``self._container``). The data-platform ``WorkloadBase.exec()``
                # wrapper — ``self.workload.exec(...)``, ``self.exec(...)`` — blocks
                # internally (subprocess, or an internal ``.wait_output()``) and
                # returns a str, so discarding its result is correct. Gating on the
                # receiver name keeps those wrappers from being flagged. This can
                # miss a container bound to an unconventional name, but that trade
                # avoids a large volume of false positives on the wrapper idiom.
                name = ast_.receiver(call)
                if name is None:
                    continue
                lname = name.lower()
                if not (lname == "container" or lname.endswith("_container")):
                    continue
                diagnostics.append(
                    self.diagnostic(
                        "container.exec() result not consumed — the process runs "
                        "asynchronously, no exit code is checked, and a full "
                        "stdout/stderr buffer can stall the container",
                        path=module.path,
                        line=call.lineno,
                        fix_hint=(
                            "Chain `.wait()` or `.wait_output()` on the call, "
                            "or assign the result and call `.wait*()` on it later"
                        ),
                    )
                )
        return diagnostics
