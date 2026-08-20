"""Status rules — how a charm reports its state to Juju."""

import ast
import pathlib

from .. import _models as models
from ._base import Rule

# Juju delivers each of these events at most once per unit lifetime, and
# never re-delivers one because the unit's state changed. A charm that
# swallows a failure here and reports ``BlockedStatus`` instead is
# stranded: the operator fixes the underlying problem, but the event
# that would act on the fix never arrives again.
_NON_REPEATING_EVENTS = frozenset({"install", "start", "stop", "remove"})


def _lifecycle_event(event_expr: ast.AST) -> str | None:
    """Return the observed event name, or ``None`` if it can't be named.

    Only the plain ``<...>.on.<event>`` attribute form is recognised —
    that is how every charm observes the lifecycle events. Any other
    expression (a subscript, a ``getattr``, a bound event held in a
    variable) yields ``None``, which the caller treats as "this handler
    also runs for something we can't identify" and therefore does not
    flag.
    """
    if not isinstance(event_expr, ast.Attribute):
        return None
    parent = event_expr.value
    if isinstance(parent, ast.Attribute) and parent.attr == "on":
        return event_expr.attr
    return None


def _handler_name(handler_expr: ast.AST) -> str | None:
    """Return the name of the function passed as an observer, else ``None``."""
    if isinstance(handler_expr, ast.Attribute):
        return handler_expr.attr
    if isinstance(handler_expr, ast.Name):
        return handler_expr.id
    return None


def _handler_events(tree: ast.AST) -> dict[str, set[str | None]]:
    """Map each observed handler name to the set of events it is observed for.

    ``None`` in the set marks an observe call whose event expression
    could not be named.
    """
    events: dict[str, set[str | None]] = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr != "observe" or len(node.args) < 2:
            continue
        handler = _handler_name(node.args[1])
        if handler is None:
            continue
        events.setdefault(handler, set()).add(_lifecycle_event(node.args[0]))
    return events


def _is_blocked_status(node: ast.AST) -> bool:
    """Return whether *node* constructs a ``BlockedStatus``."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "BlockedStatus"
    if isinstance(func, ast.Attribute):
        return func.attr == "BlockedStatus"
    return False


def _is_status_assignment(node: ast.AST) -> bool:
    """Return whether *node* assigns a ``BlockedStatus`` to a ``.status`` attribute.

    Covers the ``self.unit.status = BlockedStatus(...)`` idiom and its
    ``self.app.status`` counterpart, annotated or not.
    """
    if isinstance(node, ast.Assign):
        return _is_blocked_status(node.value) and any(
            isinstance(target, ast.Attribute) and target.attr == "status"
            for target in node.targets
        )
    if isinstance(node, ast.AnnAssign):
        return (
            node.value is not None
            and _is_blocked_status(node.value)
            and isinstance(node.target, ast.Attribute)
            and node.target.attr == "status"
        )
    return False


def _is_add_status_call(node: ast.AST) -> bool:
    """Return whether *node* is ``<event>.add_status(BlockedStatus(...))``."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_status"
        and bool(node.args)
        and _is_blocked_status(node.args[0])
    )


def _blocked_status_lines(func: ast.AST) -> list[int]:
    """Return the lines in *func* that report ``BlockedStatus``."""
    lines = {
        node.lineno
        for node in ast.walk(func)
        # The isinstance check is redundant for the predicates below, but it
        # is what tells the type checker the node carries a ``lineno``.
        if isinstance(node, ast.Assign | ast.AnnAssign | ast.Call)
        and (_is_status_assignment(node) or _is_add_status_call(node))
    }
    return sorted(lines)


class BlockedStatusInNonRepeatingHandler(Rule):
    """Detect ``BlockedStatus`` reported from a handler that Juju won't run again.

    A handler is only flagged when *every* event it is observed against
    is non-repeating. Charms commonly point one reconciler at ``install``
    and at ``config-changed`` or ``update-status`` as well; those recover
    on the next event, so they are left alone. The same applies when an
    observe call's event expression can't be named statically — an
    unknown event is assumed to be a recovering one.
    """

    category = "STATUS"
    number = 1
    name = "blocked-status-in-non-repeating-handler"
    description = "BlockedStatus set in an install/start/stop/remove handler"
    default_severity = models.Severity.WARNING
    reference_url = "https://documentation.ubuntu.com/juju/latest/reference/hook/#install"

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        for path, content in sorted(context.python_sources.items()):
            if "lib" in path.relative_to(context.charm_dir).parts:
                continue
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue
            diagnostics.extend(self._check_module(path, tree))
        return diagnostics

    def _check_module(self, path: pathlib.Path, tree: ast.AST) -> list[models.Diagnostic]:
        handler_events = _handler_events(tree)
        diagnostics: list[models.Diagnostic] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            observed = handler_events.get(node.name)
            if not observed or not observed <= _NON_REPEATING_EVENTS:
                continue
            event = "/".join(sorted(e for e in observed if e is not None))
            diagnostics.extend(
                self.diagnostic(
                    f"BlockedStatus set in '{node.name}', observed for '{event}' "
                    f"— Juju does not re-emit {event}, so the charm cannot recover "
                    f"once the operator fixes the problem",
                    path=str(path),
                    line=line,
                    fix_hint=(
                        "let the exception propagate so the hook fails and Juju "
                        "retries it (or the operator runs `juju resolved`)"
                    ),
                )
                for line in _blocked_status_lines(node)
            )
        return diagnostics
