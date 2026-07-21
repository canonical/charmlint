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


def _self_method_name(node: ast.AST) -> str | None:
    """Pull ``X`` out of ``self.X`` attribute access, else ``None``."""
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
    ):
        return node.attr
    return None


def _walk_observe_calls(tree: ast.AST) -> list[tuple[str, str | None]]:
    """Yield ``(action_name_hyphenated, handler_method_or_None)`` per observe call."""
    found: list[tuple[str, str | None]] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr != "observe" or len(node.args) < 2:
            continue
        action = _action_from_event_expr(node.args[0])
        if action is None:
            continue
        handler = _self_method_name(node.args[1])
        found.append((action, handler))
    return found


def _collect_methods(tree: ast.AST) -> dict[str, ast.FunctionDef]:
    """Map every class-method name in the tree to its ``FunctionDef`` node."""
    methods: dict[str, ast.FunctionDef] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                methods[item.name] = item
    return methods


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
        for action, _handler in _walk_observe_calls(tree):
            out.add(action)
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
