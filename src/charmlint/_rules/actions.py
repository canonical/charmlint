"""Action rules — declared actions vs. observers wired up in src/."""

import ast
import pathlib

from .. import _models as models
from ._base import Rule


def _action_from_event_expr(event_expr: ast.AST) -> str | None:
    """Return the hyphenated action name from an action-event expression, else ``None``.

    ``event_expr`` is whatever expression node appears as the first
    argument to a ``framework.observe(...)`` call. Recognises the
    three forms accepted by ops:

    * ``self.on.<action>_action`` — plain attribute access.
    * ``self.on['<action>'].action`` — subscript returns a
      ``PrefixedEvents`` wrapper whose ``.action`` is the same
      ``BoundEvent`` as the attribute form.
    * ``getattr(self.on, '<action>_action')`` — dynamic attribute
      lookup; common in charms that build the event reference from
      a constant.

    Only literal string keys in Form 2 are recognised — a named-constant
    reference like ``self.on[FOO_ACTION].action`` won't match, because the
    AST sees an ``ast.Name``, not ``ast.Constant``.
    """
    # Form 0: getattr(<...>.on, '<name>_action')
    if (
        isinstance(event_expr, ast.Call)
        and isinstance(event_expr.func, ast.Name)
        and event_expr.func.id == "getattr"
        and len(event_expr.args) >= 2
    ):
        target, key = event_expr.args[0], event_expr.args[1]
        if (
            isinstance(target, ast.Attribute)
            and target.attr == "on"
            and isinstance(key, ast.Constant)
            and isinstance(key.value, str)
            and key.value.endswith("_action")
        ):
            return key.value[: -len("_action")].replace("_", "-")
        return None
    # Forms 1 and 2 are attribute access on some parent — either
    # `parent.<name>_action` (Form 1) or `parent.action` where the
    # parent is a subscript (Form 2). Anything else can't be an event.
    if not isinstance(event_expr, ast.Attribute):
        return None
    parent = event_expr.value
    # Form 1: <...>.on.<name>_action
    if isinstance(parent, ast.Attribute) and parent.attr == "on":
        if event_expr.attr.endswith("_action"):
            return event_expr.attr[: -len("_action")].replace("_", "-")
        return None
    # Form 2: <...>.on['<name>'].action
    if event_expr.attr != "action":
        return None
    if not isinstance(parent, ast.Subscript):
        return None
    grandparent = parent.value
    if not (isinstance(grandparent, ast.Attribute) and grandparent.attr == "on"):
        return None
    key = parent.slice
    if isinstance(key, ast.Constant) and isinstance(key.value, str):
        return key.value
    return None


def _walk_observe_calls(tree: ast.AST) -> list[str]:
    """Yield the hyphenated action name for each observe call."""
    found: list[str] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr != "observe" or len(node.args) < 2:
            continue
        action = _action_from_event_expr(node.args[0])
        if action is None:
            continue
        found.append(action)
    return found


def _gather_action_observers(sources: dict[pathlib.Path, str]) -> set[str]:
    """Return the set of action names observed by charm sources."""
    out: set[str] = set()
    for path, content in sources.items():
        if "lib" in path.parts:
            continue
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue
        out.update(_walk_observe_calls(tree))
    return out


class ActionMissingObserver(Rule):
    """Every declared action must have a ``framework.observe`` registration.

    Only observe calls in the charm's own ``src/`` are considered.
    Charms whose observe calls live in an external base class (installed
    as a pip dependency, not vendored under ``src/`` or ``lib/``) will
    hit false positives — disable ACTIONS-001 in that case.
    """

    category = "ACTIONS"
    number = 1
    name = "action-missing-observer"
    description = "Action declared in charmcraft.yaml has no observer in src/"
    default_severity = models.Severity.WARNING

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        if not context.actions:
            return []
        observers = _gather_action_observers(context.python_sources)
        diagnostics: list[models.Diagnostic] = []
        for action_name in context.actions:
            if action_name in observers:
                continue
            handler = "_on_" + action_name.replace("-", "_")
            diagnostics.append(
                self.diagnostic(
                    f"Action '{action_name}' has no observer "
                    f"(expected `framework.observe(self.on['{action_name}'].action, ...)`)",
                    fix_hint=(
                        f"Add `framework.observe(self.on['{action_name}'].action, "
                        f"self.{handler})` in __init__ and a matching handler"
                    ),
                )
            )
        return diagnostics


class ActionMissingAdditionalProperties(Rule):
    """Every declared action should state ``additionalProperties`` explicitly.

    Juju 4 flipped the default relative to Juju 3, so an action that
    omits the field accepts unknown parameters on one version and
    rejects them on the other. Either value silences the rule — the
    point is that the charm has made the choice, not that it made a
    particular one.

    Actions declared without a body (``do-thing:`` with no mapping) are
    flagged too: they have no ``additionalProperties`` either.
    """

    category = "ACTIONS"
    number = 2
    name = "action-missing-additional-properties"
    description = "Action does not explicitly set 'additionalProperties'"
    default_severity = models.Severity.WARNING
    reference_url = "https://canonical.com/juju/docs/charmcraft/stable/reference/files/charmcraft-yaml-file/#charmcraft-yaml-key-actions"

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        for action_name, body in context.actions.items():
            if "additionalProperties" in body:
                continue
            diagnostics.append(
                self.diagnostic(
                    f"Action '{action_name}' does not set 'additionalProperties' — "
                    f"Juju 3 and Juju 4 default it differently",
                    fix_hint=(
                        f"Add `additionalProperties: false` to '{action_name}' "
                        f"(or `true` if unknown parameters are intended)"
                    ),
                )
            )
        return diagnostics
