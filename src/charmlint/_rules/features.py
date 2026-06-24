"""Feature rules — expected charm features that are commonly missing."""

import ast

from .. import models
from . import Rule


def _observe_event_name(call: ast.Call) -> str | None:
    """If ``call`` is a ``framework.observe(<event>, ...)``, return the trailing event attribute name.

    For example, ``self.framework.observe(self.on.leader_elected, handler)``
    returns ``"leader_elected"``.
    """
    func = call.func
    if not (isinstance(func, ast.Attribute) and func.attr == "observe"):
        return None
    if not call.args:
        return None
    event = call.args[0]
    if isinstance(event, ast.Attribute):
        return event.attr
    return None


class NoLeaderElectedHandler(Rule):
    """Flag stateful charms (peer relation declared) with no ``leader-elected`` observer."""

    id = "FEAT006"
    name = "no-leader-elected-handler"
    description = "Charm declares a peer relation but does not observe leader-elected"
    default_severity = models.Severity.INFO

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        peers = context.metadata.get("peers")
        if not isinstance(peers, dict) or not peers:
            return []

        for path, content in context.python_sources.items():
            if "lib" in path.parts:
                continue
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and _observe_event_name(node) == "leader_elected":
                    return []

        return [
            self.diagnostic(
                "Charm declares a `peers:` relation but does not observe "
                "`self.on.leader_elected` — peer state changes after leadership "
                "transitions may go unhandled",
                fix_hint=(
                    "Add `self.framework.observe(self.on.leader_elected, "
                    "self._on_leader_elected)` in __init__ and implement the handler"
                ),
            )
        ]
