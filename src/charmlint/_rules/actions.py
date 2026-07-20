"""Action rules — declared actions vs. observers wired up in src/."""

import ast
import pathlib

from .. import _models as models
from ._base import Rule


def _event_attr_name(node: ast.AST) -> str | None:
    """Pull ``X`` out of ``<...>.on.X`` attribute access, else ``None``."""
    if not isinstance(node, ast.Attribute):
        return None
    parent = node.value
    if not (isinstance(parent, ast.Attribute) and parent.attr == "on"):
        return None
    return node.attr


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
    """Yield ``(action_name_underscored, handler_method_or_None)`` per observe call."""
    found: list[tuple[str, str | None]] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr != "observe" or len(node.args) < 2:
            continue
        event = _event_attr_name(node.args[0])
        if event is None or not event.endswith("_action"):
            continue
        handler = _self_method_name(node.args[1])
        action = event[: -len("_action")]
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


def _gather_action_observers(
    sources: dict[pathlib.Path, str],
) -> dict[str, tuple[str | None, ast.FunctionDef | None, pathlib.Path]]:
    """Return ``{action: (handler_name, handler_node, source_path)}`` for charm sources."""
    out: dict[str, tuple[str | None, ast.FunctionDef | None, pathlib.Path]] = {}
    for path, content in sources.items():
        if "lib" in path.parts:
            continue
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue
        methods = _collect_methods(tree)
        for action, handler_name in _walk_observe_calls(tree):
            handler_node = methods.get(handler_name) if handler_name else None
            out.setdefault(action, (handler_name, handler_node, path))
    return out


class ActionMissingObserver(Rule):
    """Every declared action must have a ``framework.observe`` registration."""

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
            normalised = action_name.replace("-", "_")
            if normalised in observers:
                continue
            diagnostics.append(
                self.diagnostic(
                    f"Action '{action_name}' has no observer "
                    f"(expected `self.framework.observe(self.on.{normalised}_action, ...)`)",
                    fix_hint=(
                        f"Add `self.framework.observe(self.on.{normalised}_action, "
                        f"self._on_{normalised})` in __init__ and a matching handler"
                    ),
                )
            )
        return diagnostics
