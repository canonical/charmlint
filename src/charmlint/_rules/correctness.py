"""Correctness rules — runtime-correctness issues in charm source."""

import ast

from .. import _ast
from .. import _models as models
from ._base import Rule

# Events whose `defer()` raises RuntimeError. `stop`, `remove`,
# `secret-expired` and `secret-rotate` override `defer()` in `ops.charm`;
# `pre-commit`, `commit`, `collect-unit-status` and `collect-app-status`
# are `LifecycleEvent`s, which raise from the base override in
# `ops.framework`. Action events are handled separately, by suffix.
_NON_DEFERRABLE_EVENTS = frozenset(
    {
        "stop",
        "remove",
        "secret_expired",
        "secret_rotate",
        "pre_commit",
        "commit",
        "collect_unit_status",
        "collect_app_status",
    }
)


def _is_non_deferrable(event: str) -> bool:
    """Whether ops raises from ``defer()`` on the event named *event*."""
    return event in _NON_DEFERRABLE_EVENTS or event.endswith("_action")


def _non_deferrable_handlers(module: models.Module) -> dict[str, str]:
    """Map handler method name -> non-deferrable event it is registered for."""
    handlers: dict[str, str] = {}
    for observer in _ast.observers(module):
        if observer.event is None or observer.handler is None:
            continue
        if _is_non_deferrable(observer.event):
            handlers[observer.handler] = observer.event
    return handlers


def _defer_calls(func: ast.FunctionDef | ast.AsyncFunctionDef, event: str) -> list[ast.Call]:
    """Return every ``<event>.defer()`` call in *func*, in walk order.

    Nested function definitions are walked as well: a ``defer()`` inside a
    closure still runs as part of the handler.
    """
    return [
        node
        for node in ast.walk(func)
        if isinstance(node, ast.Call)
        and not node.args
        and not node.keywords
        and _ast.call_target(node) == f"{event}.defer"
    ]


class NonDeferrableEventDeferred(Rule):
    """Flag ``event.defer()`` inside a handler for a non-deferrable event.

    Only handlers registered as ``self.<handler>`` in a
    ``framework.observe(...)`` call are matched, and only ``defer()`` on a
    plain local name (the handler's event argument) counts — deferring a
    *different* event that was stashed on ``self`` isn't this bug.

    A handler observing both a deferrable and a non-deferrable event is
    still flagged: the ``defer()`` raises whenever the non-deferrable
    event is the one being dispatched.
    """

    category = "CORRECTNESS"
    number = 4
    name = "non-deferrable-event-deferred"
    description = "event.defer() called in a handler for a non-deferrable event"
    default_severity = models.Severity.ERROR
    reference_url = (
        "https://canonical.com/juju/docs/ops/latest/explanation/defer-guidance/"
        "#not-possible-actions-shutting-down-framework-generated-events-secrets"
    )

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        for module in context.charm_sources():
            diagnostics.extend(self._check_module(module))
        return diagnostics

    def _check_module(self, module: models.Module) -> list[models.Diagnostic]:
        handlers = _non_deferrable_handlers(module)
        if not handlers:
            return []
        diagnostics: list[models.Diagnostic] = []
        for func in module.functions():
            event = handlers.get(func.name)
            if event is None:
                continue
            # The event argument is the handler's second parameter; a
            # `defer()` on any other local name is a different object.
            params = [arg.arg for arg in func.args.args]
            if len(params) < 2:
                continue
            event_param = params[1]
            pretty = event.replace("_", "-")
            for call in _defer_calls(func, event_param):
                diagnostics.append(
                    self.diagnostic(
                        f"'{func.name}' calls {event_param}.defer(), but is registered for "
                        f"'{pretty}', which cannot be deferred — this raises RuntimeError "
                        f"at runtime",
                        path=module.path,
                        line=call.lineno,
                        fix_hint=(
                            "Remove the defer() call: handle the condition inline, retry "
                            "briefly, or (for actions) fail the action with a message"
                        ),
                    )
                )
        return diagnostics
