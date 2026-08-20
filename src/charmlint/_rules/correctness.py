"""Correctness rules — runtime-correctness issues in charm source."""

import ast
import dataclasses
import pathlib
from collections.abc import Callable

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
        def is_non_return(nxt: ast.stmt | None) -> bool:
            # A following `raise` is a defer that never persists; that case
            # is reported by CORRECTNESS-002, so exclude it here rather than
            # emit a second diagnostic on the same line.
            return nxt is not None and not isinstance(nxt, ast.Return | ast.Raise)

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
        def is_raise(nxt: ast.stmt | None) -> bool:
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
            for path, line in _find_defers_followed_by(context, match_next=is_raise)
        ]


def _find_defers_followed_by(
    context: models.CharmContext,
    match_next: Callable[[ast.stmt | None], bool],
) -> list[tuple[str, int]]:
    """Find each ``event.defer()`` whose next sibling statement matches ``match_next``.

    ``match_next`` receives the statement that executes immediately after
    the ``event.defer()`` - its next sibling in the same block, or, when the
    ``defer()`` is the last statement in its block, whatever runs once that
    block completes (``None`` if control then leaves the function/module).
    Returns ``(path, lineno)`` for each matching ``event.defer()``.
    """
    hits: list[tuple[str, int]] = []
    for path, tree in _iter_charm_sources(context):
        visit = _DeferVisitor(hits=hits, match_next=match_next, path=str(path))
        _walk_bodies(tree.body, after=None, visit=visit)
    return hits


def _iter_charm_sources(
    context: models.CharmContext,
) -> list[tuple[pathlib.Path, ast.Module]]:
    """Parse every source outside the top-level ``lib/``; skip files that fail to parse."""
    parsed: list[tuple[pathlib.Path, ast.Module]] = []
    for path, content in context.python_sources.items():
        # `lib/` at the charm root holds `charmcraft fetch-lib` output — other
        # people's code. A `src/lib/` package is the charm's own, so lint it.
        if path.relative_to(context.charm_dir).parts[0] == "lib":
            continue
        try:
            parsed.append((path, ast.parse(content)))
        except SyntaxError:
            continue
    return parsed


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
        if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            # A def/class body runs in its own scope; a trailing statement there
            # returns from that scope rather than continuing to the next statement.
            nested_after = None
        elif idx + 1 < len(body):
            # This isn't the last statement in this body, so the next sibling follows.
            nested_after = body[idx + 1]
        else:
            # This is the last statement, so the body's own 'after' follows.
            nested_after = after
        # Recurse into every nested statement list this node exposes:
        # `body` (if/for/while/with/def/class suites), `orelse` (else/elif
        # and for/while-else), and `finalbody` (the `finally` suite).
        for attr in ("body", "orelse", "finalbody"):
            inner = getattr(stmt, attr, None)
            # The list check is load-bearing here, not just defensive: on
            # `lambda` and conditional expressions `body` is a single
            # expression node rather than a statement list.
            if isinstance(inner, list):
                _walk_bodies(inner, after=nested_after, visit=visit)
        # `handlers` holds the `except` clauses of a `try`; each has its
        # own suite in `handler.body`. Unlike `body` above, it is always a
        # list where it exists at all, so absent is the only other case.
        for handler in getattr(stmt, "handlers", []):
            _walk_bodies(handler.body, after=nested_after, visit=visit)


@dataclasses.dataclass
class _DeferVisitor:
    """Collect ``(path, lineno)`` for each ``event.defer()`` matching ``match_next``."""

    hits: list[tuple[str, int]]
    match_next: Callable[[ast.stmt | None], bool]
    path: str

    def __call__(self, body: list[ast.stmt], after: ast.stmt | None) -> None:
        for idx, stmt in enumerate(body):
            if not _is_event_defer(stmt):
                continue
            nxt = body[idx + 1] if idx + 1 < len(body) else after
            if self.match_next(nxt):
                self.hits.append((self.path, stmt.lineno))


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
