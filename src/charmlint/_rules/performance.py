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

_FOR_LOOPS = (ast.For, ast.AsyncFor)
_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)


class LoggingInLoop(Rule):
    """Check for logging calls inside a loop over relations or units.

    Under Juju, ops sends each log record to the controller by running the
    ``juju-log`` hook tool, which is a subprocess. A loop that logs on every
    iteration therefore starts a process per iteration. That's cheap for a
    handful of items, but a loop over relations or units grows with the
    deployment, and a charm at the centre of a large one (an aggregator
    with hundreds of relations, say) can spend most of a hook in
    ``juju-log``.

    The rule looks at ``for`` loops whose iterable names a relation or
    units (``self.model.relations[...]``, ``relation.units``,
    ``self._peer_relations()``, ``relation_ids``, ...). Loops over other
    collections, ``while`` loops, and retry loops usually run a few times,
    so they aren't reported. It reports once per outermost such loop, at
    the first logging call in its body, and says how many calls there are.
    It recognises calls on a receiver named like a logger (``logger``,
    ``log``, ``logging``, ``self._logger``, ...) using the standard level
    methods. Calls in a nested function, class or lambda defined in the
    loop are not counted, because they don't necessarily run once per
    iteration. Comprehensions and the ``else`` clause of a loop are not
    examined.

    Move the logging out of the loop (log a summary afterwards), or limit it
    to the exceptional case. Logging a rare failure inside a loop is
    reasonable; suppress the finding with a ``# charmlint: ignore`` comment if so.
    """

    category = "PERFORMANCE"
    number = 1
    name = "logging-in-loop"
    description = "Logging inside a loop over relations or units runs juju-log once per iteration"
    default_severity = models.Severity.WARNING

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        for module in context.charm_sources():
            for loop in _outermost_relation_loops(module.tree):
                calls = _logging_calls(loop)
                if not calls:
                    continue
                count = len(calls)
                noun = "call" if count == 1 else "calls"
                diagnostics.append(
                    self.diagnostic(
                        f"{count} logging {noun} inside a loop over relations or units; each "
                        "one runs juju-log as a subprocess on every iteration",
                        path=module.path,
                        line=calls[0].lineno,
                        fix_hint="Log once before or after the loop, or only on the unusual path",
                    )
                )
        return diagnostics


def _outermost_relation_loops(tree: ast.AST) -> list[ast.stmt]:
    """Return the loops over relations or units not nested in another such loop.

    A loop inside a function that is itself inside a loop counts as
    outermost: the function body does not necessarily run per iteration.
    """
    found: list[ast.stmt] = []

    def visit(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, _FOR_LOOPS) and _iterates_relations(child.iter):
                found.append(child)
                # Loops nested inside a function defined in this loop start fresh.
                for inner in _nested_scopes(child):
                    visit(inner)
            else:
                visit(child)

    visit(tree)
    return found


def _iterates_relations(iterable: ast.expr) -> bool:
    """Whether *iterable* names relations or units, so grows with the deployment.

    A literal list or tuple is a fixed set of items, even when one of
    them is named after a relation (a list of reconcile steps, say).
    """
    if isinstance(iterable, (ast.List, ast.Tuple, ast.Set)):
        return False
    for node in ast.walk(iterable):
        if isinstance(node, ast.Name):
            name = node.id
        elif isinstance(node, ast.Attribute):
            name = node.attr
        else:
            continue
        lowered = name.lower()
        if "relation" in lowered or lowered == "units" or lowered.endswith("_units"):
            return True
    return False


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
