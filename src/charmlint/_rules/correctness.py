"""Correctness rules — runtime-correctness issues in charm source."""

import ast
import pathlib
from collections.abc import Callable

from .. import _models as models
from ._base import Rule


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


def _walk_bodies(body: list[ast.stmt], visit: Callable[[list[ast.stmt]], None]) -> None:
    """Call ``visit`` on ``body`` and every nested statement list."""
    visit(body)
    for stmt in body:
        for attr in ("body", "orelse", "finalbody"):
            inner = getattr(stmt, attr, None)
            if isinstance(inner, list):
                _walk_bodies(inner, visit)
        handlers = getattr(stmt, "handlers", None)
        if isinstance(handlers, list):
            for handler in handlers:
                _walk_bodies(handler.body, visit)


def _iter_charm_sources(
    context: models.CharmContext,
) -> list[tuple[pathlib.Path, ast.Module]]:
    """Parse every non-``lib/`` Python source; skip files that fail to parse."""
    parsed: list[tuple[pathlib.Path, ast.Module]] = []
    for path, content in context.python_sources.items():
        if "lib" in path.relative_to(context.charm_dir).parts:
            continue
        try:
            parsed.append((path, ast.parse(content)))
        except SyntaxError:
            continue
    return parsed


class DeferWithoutReturn(Rule):
    """Flag ``event.defer()`` not immediately followed by ``return`` or ``raise``."""

    category = "CORRECTNESS"
    number = 1
    name = "defer-without-return"
    description = "event.defer() not immediately followed by return or raise"
    default_severity = models.Severity.WARNING

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        for path, tree in _iter_charm_sources(context):

            def visit(body: list[ast.stmt], *, _path: str = str(path)) -> None:
                for idx, stmt in enumerate(body):
                    if (
                        _is_event_defer(stmt)
                        and idx < len(body) - 1
                        and not isinstance(body[idx + 1], ast.Return | ast.Raise)
                    ):
                        diagnostics.append(
                            self.diagnostic(
                                "event.defer() is not immediately followed by "
                                "`return` or `raise` — the handler keeps "
                                "executing after deferring, so any subsequent "
                                "side effects run both now and on the "
                                "deferred retry",
                                path=_path,
                                line=stmt.lineno,
                                fix_hint=(
                                    "Add `return` immediately after "
                                    "`event.defer()` so the handler exits "
                                    "cleanly and the deferred retry is the "
                                    "only execution that performs follow-up "
                                    "work"
                                ),
                            )
                        )

            _walk_bodies(tree.body, visit)
        return diagnostics


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
        diagnostics: list[models.Diagnostic] = []
        for path, tree in _iter_charm_sources(context):

            def visit(body: list[ast.stmt], *, _path: str = str(path)) -> None:
                for idx, stmt in enumerate(body):
                    if (
                        _is_event_defer(stmt)
                        and idx < len(body) - 1
                        and isinstance(body[idx + 1], ast.Raise)
                    ):
                        diagnostics.append(
                            self.diagnostic(
                                "event.defer() is immediately followed by "
                                "`raise` — the exception aborts the framework "
                                "commit, so the defer never persists and the "
                                "event will not be re-emitted",
                                path=_path,
                                line=stmt.lineno,
                                fix_hint=(
                                    "Either drop the `event.defer()` (if the "
                                    "failure should propagate) or replace the "
                                    "`raise` with `return` (if the event "
                                    "should be retried)"
                                ),
                            )
                        )

            _walk_bodies(tree.body, visit)
        return diagnostics
