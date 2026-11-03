"""Performance rules — patterns that make a charm slow at scale."""

import ast

from .. import _ast
from .. import _models as models
from ._base import Rule

# Method names that emit a log record on a standard-library logger.
_LOG_METHODS = frozenset({
    "debug",
    "info",
    "warning",
    "warn",
    "error",
    "critical",
    "fatal",
    "exception",
    "log",
})

# Receiver names that, by convention, hold a logger. Compared after
# lower-casing and stripping underscores, so ``LOGGER`` and ``_logger`` match.
_LOGGER_NAMES = frozenset({"logger", "log", "logging"})

_LOOPS = (ast.For, ast.AsyncFor, ast.While)
_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)


class LoggingInLoop(Rule):
    """Check for logging calls made inside a ``for`` or ``while`` loop.

    Under Juju, ops sends each log record to the controller by running the
    ``juju-log`` hook tool, which is a subprocess. A loop that logs on every
    iteration therefore starts a process per iteration. That is cheap for a
    handful of items and very slow for hundreds, for example when iterating
    over every relation of a charm that sits in the middle of a large
    deployment.

    The rule reports once per outermost loop, at the first logging call in
    its body, and says how many calls there are. It recognises calls on a
    receiver named like a logger (``logger``, ``log``, ``logging``,
    ``self._logger``, ...) using the standard level methods. Calls in a
    nested function, class or lambda defined in the loop are not counted,
    because they do not necessarily run once per iteration. Comprehensions
    and the ``else`` clause of a loop are not examined.

    Move the logging out of the loop (log a summary afterwards), or limit it
    to the exceptional case. Logging a rare failure inside a loop is
    reasonable; suppress the finding with a ``# charmlint: ignore`` comment if so.
    """

    category = "PERFORMANCE"
    number = 1
    name = "logging-in-loop"
    description = "Logging inside a loop runs juju-log once per iteration"
    default_severity = models.Severity.INFO

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        for module in context.charm_sources():
            for loop in _outermost_loops(module.tree):
                calls = _logging_calls(loop)
                if not calls:
                    continue
                count = len(calls)
                noun = "call" if count == 1 else "calls"
                diagnostics.append(
                    self.diagnostic(
                        f"{count} logging {noun} inside a loop; each one runs juju-log "
                        "as a subprocess on every iteration.",
                        path=module.path,
                        line=calls[0].lineno,
                        fix_hint="Log once before or after the loop, or only on the unusual path.",
                    )
                )
        return diagnostics


def _outermost_loops(tree: ast.AST) -> list[ast.stmt]:
    """Return the loops in *tree* that are not nested inside another loop.

    A loop inside a function that is itself inside a loop counts as
    outermost: the function body does not necessarily run per iteration.
    """
    found: list[ast.stmt] = []

    def visit(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, _LOOPS):
                found.append(child)
                # Loops nested inside a function defined in this loop start fresh.
                for inner in _nested_scopes(child):
                    visit(inner)
            else:
                visit(child)

    visit(tree)
    return found


def _nested_scopes(loop: ast.stmt) -> list[ast.AST]:
    """Return the function, class and lambda nodes reachable from *loop*'s body."""
    scopes: list[ast.AST] = []

    def visit(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, _SCOPES):
                scopes.append(child)
            else:
                visit(child)

    for statement in getattr(loop, "body", []):
        if isinstance(statement, _SCOPES):
            scopes.append(statement)
        else:
            visit(statement)
    return scopes


def _logging_calls(loop: ast.stmt) -> list[ast.Call]:
    """Return the logging calls that run on each iteration of *loop*."""
    calls: list[ast.Call] = []

    def visit(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, _SCOPES):
                continue
            if isinstance(child, ast.Call) and _is_logging_call(child):
                calls.append(child)
            visit(child)

    # Only the body runs on every iteration: a ``for`` iterable is evaluated
    # once and an ``else`` clause runs at most once.
    for statement in getattr(loop, "body", []):
        if not isinstance(statement, _SCOPES):
            visit(statement)
    return sorted(calls, key=lambda call: (call.lineno, call.col_offset))


def _is_logging_call(call: ast.Call) -> bool:
    if not isinstance(call.func, ast.Attribute) or call.func.attr not in _LOG_METHODS:
        return False
    name = _ast.receiver(call)
    return name is not None and name.replace("_", "").lower() in _LOGGER_NAMES
