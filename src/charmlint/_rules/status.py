"""Status rules — how a charm reports its state to Juju."""

import ast

from .. import _ast
from .. import _models as models
from ._base import Rule

# Juju delivers each of these events at most once per unit lifetime, and
# never re-delivers one because the unit's state changed. A charm that
# swallows a failure here and reports ``BlockedStatus`` instead is
# stranded: the operator fixes the underlying problem, but the event
# that would act on the fix never arrives again.
_NON_REPEATING_EVENTS = frozenset({"install", "start", "stop", "remove"})


def _non_repeating_handlers(module: models.Module) -> dict[str, set[str]]:
    """Map each handler in *module* to the non-repeating events it observes.

    A handler appears only when *every* observe call that names it resolves
    to a non-repeating event. One repeating event — or one observe call
    whose event expression could not be read statically — is enough to
    leave the handler out, because either means the charm gets another go.
    """
    events: dict[str, set[str]] = {}
    excluded: set[str] = set()
    for observer in _ast.observers(module):
        if observer.handler is None:
            continue
        if not observer.resolved or observer.event not in _NON_REPEATING_EVENTS:
            excluded.add(observer.handler)
            continue
        events.setdefault(observer.handler, set()).add(observer.event)
    return {handler: found for handler, found in events.items() if handler not in excluded}


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
    observe call's event expression can't be resolved statically — an
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
        for module in context.charm_sources():
            diagnostics.extend(self._check_module(module))
        return diagnostics

    def _check_module(self, module: models.Module) -> list[models.Diagnostic]:
        handlers = _non_repeating_handlers(module)
        diagnostics: list[models.Diagnostic] = []
        for func in module.functions():
            observed = handlers.get(func.name)
            if not observed:
                continue
            event = "/".join(sorted(observed))
            diagnostics.extend(
                self.diagnostic(
                    f"BlockedStatus set in '{func.name}', observed for '{event}' "
                    f"— Juju does not re-emit {event}, so the charm cannot recover "
                    f"once the operator fixes the problem",
                    path=module.path,
                    line=line,
                    fix_hint=(
                        "let the exception propagate so the hook fails and Juju "
                        "retries it (or the operator runs `juju resolved`)"
                    ),
                )
                for line in _blocked_status_lines(func)
            )
        return diagnostics
