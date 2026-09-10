"""Correctness rules — runtime-correctness issues in charm source."""

import ast
from collections.abc import Callable

from .. import _ast
from .. import _models as models
from ._base import Rule


class DeferWithoutReturn(Rule):
    """Flag ``event.defer()`` not immediately followed by ``return``."""

    category = "CORRECTNESS"
    number = 1
    name = "defer-without-return"
    description = "event.defer() not immediately followed by return"
    default_severity = models.Severity.WARNING

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        def is_non_return(following: ast.stmt | None) -> bool:
            # A following `raise` is a defer that never persists; that case
            # is reported by CORRECTNESS-002, so exclude it here rather than
            # emit a second diagnostic on the same line.
            return following is not None and not isinstance(following, ast.Return | ast.Raise)

        return [
            self.diagnostic(
                "event.defer() is not immediately followed by "
                "`return` — the handler keeps "
                "executing after deferring, so any subsequent "
                "side effects run both now and on the "
                "deferred retry",
                path=path,
                line=line,
                fix_hint=(
                    "Add `return` immediately after "
                    "`event.defer()` so the handler exits "
                    "cleanly and the deferred retry is the "
                    "only execution that performs follow-up "
                    "work"
                ),
            )
            for path, line in _find_defers_followed_by(context, match_next=is_non_return)
        ]


class DeferBeforeRaise(Rule):
    """Flag ``event.defer()`` immediately followed by ``raise``.

    An uncaught exception during a hook aborts the framework commit, so
    the ``defer()`` never persists — the event will not be re-emitted.
    Either raise without deferring (if the failure should propagate) or
    defer and return (if the event should be retried).
    """

    category = "CORRECTNESS"
    number = 2
    name = "defer-before-raise"
    description = "event.defer() immediately followed by raise"
    default_severity = models.Severity.WARNING

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        def is_raise(following: ast.stmt | None) -> bool:
            return isinstance(following, ast.Raise)

        return [
            self.diagnostic(
                "event.defer() is immediately followed by "
                "`raise` — the exception aborts the framework "
                "commit, so the defer never persists and the "
                "event will not be re-emitted",
                path=path,
                line=line,
                fix_hint=(
                    "Either drop the `event.defer()` (if the "
                    "failure should propagate) or replace the "
                    "`raise` with `return` (if the event "
                    "should be retried)"
                ),
            )
            for path, line in _find_defers_followed_by(context, match_next=is_raise)
        ]


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
                target = _ast.call_target(call)
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
                name = _ast.receiver(call)
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


def _find_defers_followed_by(
    context: models.CharmContext,
    match_next: Callable[[ast.stmt | None], bool],
) -> list[tuple[str, int]]:
    """Find each ``event.defer()`` whose continuation matches ``match_next``.

    ``match_next`` receives the statement that executes immediately after
    the ``event.defer()`` — its next sibling in the same block, or, when the
    ``defer()`` is the last statement in its block, whatever runs once that
    block completes (``None`` if control then leaves the function/module).
    Returns ``(path, lineno)`` for each matching ``event.defer()``.
    """
    return [
        (str(module.file), statement.lineno)
        for module in context.charm_sources()
        for statement, following in _ast.walk_statements(module.tree.body)
        if _is_event_defer(statement) and match_next(following)
    ]


def _is_event_defer(node: ast.AST) -> bool:
    """True if ``node`` is the statement ``event.defer()``."""
    if not isinstance(node, ast.Expr):
        return False
    call = node.value
    return (
        isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr == "defer"
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == "event"
        and not call.args
        and not call.keywords
    )
