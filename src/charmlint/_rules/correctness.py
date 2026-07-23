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


def _walk_bodies(
    body: list[ast.stmt],
    after: ast.stmt | None,
    visit: Callable[[list[ast.stmt], ast.stmt | None], None],
) -> None:
    """Call ``visit`` on ``body`` and every nested statement list.

    ``after`` is the statement that executes once ``body`` completes, or
    ``None`` if control then leaves the enclosing function/module. It is
    forwarded to ``visit`` so a trailing statement (e.g. an ``event.defer()``
    at the end of an ``if`` branch) can be checked against whatever actually
    runs next, rather than being treated as the end of execution.

    Loops and ``finally`` suites are approximated conservatively: a block's
    continuation is the statement following the enclosing compound
    statement, so back-edges (a loop's next iteration) and ``finally``
    ordering are not modelled. This favours false negatives over false
    positives.
    """
    visit(body, after)
    for idx, stmt in enumerate(body):
        # What runs after this statement's nested blocks complete: the next
        # sibling in this block, or - if this is the last statement - the
        # block's own continuation.
        cont = body[idx + 1] if idx + 1 < len(body) else after
        # A def/class body runs in its own scope; a trailing statement there
        # returns from that scope rather than continuing to `cont`.
        nested_after = (
            None
            if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
            else cont
        )
        # Recurse into every nested statement list this node exposes:
        # `body` (if/for/while/with/def/class suites), `orelse` (else/elif
        # and for/while-else), and `finalbody` (the `finally` suite).
        for attr in ("body", "orelse", "finalbody"):
            inner = getattr(stmt, attr, None)
            if isinstance(inner, list):
                _walk_bodies(inner, nested_after, visit)
        # `handlers` holds the `except` clauses of a `try`; each has its
        # own suite in `handler.body`.
        handlers = getattr(stmt, "handlers", None)
        if isinstance(handlers, list):
            for handler in handlers:
                _walk_bodies(handler.body, nested_after, visit)


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


def _find_defers(
    context: models.CharmContext,
    followed_by: Callable[[ast.stmt | None], bool],
) -> list[tuple[str, int]]:
    """Find each ``event.defer()`` whose next sibling statement matches ``followed_by``.

    ``followed_by`` receives the statement that executes immediately after
    the ``event.defer()`` - its next sibling in the same block, or, when the
    ``defer()`` is the last statement in its block, whatever runs once that
    block completes (``None`` if control then leaves the function/module).
    Returns ``(path, lineno)`` for each matching ``event.defer()``.
    """
    hits: list[tuple[str, int]] = []
    for path, tree in _iter_charm_sources(context):

        def visit(
            body: list[ast.stmt],
            after: ast.stmt | None,
            *,
            _path: str = str(path),
        ) -> None:
            for idx, stmt in enumerate(body):
                if not _is_event_defer(stmt):
                    continue
                nxt = body[idx + 1] if idx + 1 < len(body) else after
                if followed_by(nxt):
                    hits.append((_path, stmt.lineno))

        _walk_bodies(tree.body, None, visit)
    return hits


class DeferWithoutReturn(Rule):
    """Flag ``event.defer()`` not immediately followed by ``return`` or ``raise``."""

    category = "CORRECTNESS"
    number = 1
    name = "defer-without-return"
    description = "event.defer() not immediately followed by return or raise"
    default_severity = models.Severity.WARNING

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        def followed_by(nxt: ast.stmt | None) -> bool:
            return nxt is not None and not isinstance(nxt, ast.Return | ast.Raise)

        return [
            self.diagnostic(
                "event.defer() is not immediately followed by "
                "`return` or `raise` — the handler keeps "
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
            for path, line in _find_defers(context, followed_by)
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
        def followed_by(nxt: ast.stmt | None) -> bool:
            return isinstance(nxt, ast.Raise)

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
            for path, line in _find_defers(context, followed_by)
        ]
