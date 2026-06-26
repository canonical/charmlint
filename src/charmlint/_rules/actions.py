"""Action rules — expected operational actions and action quality.

ACT001–ACT005 live here; the ACT006/ACT007 AST helpers are added as
a gating PR; ACT006 and ACT007 follow.
"""

import ast
import pathlib
from typing import Any

from .. import _models as models
from . import Rule

# Expected operational actions with their aliases.
_EXPECTED_ACTIONS: dict[str, tuple[str, list[str]]] = {
    "ACT001": (
        "get-health",
        ["health-check", "check-health", "get-status", "health"],
    ),
    "ACT002": (
        "pause",
        ["stop", "disable"],
    ),
    "ACT003": (
        "resume",
        ["start", "enable"],
    ),
}


def _make_action_rule(_id: str, _canonical: str, _aliases: list[str]) -> type[Rule]:
    """Create a Rule subclass for a missing expected action."""
    rid, canonical, aliases = _id, _canonical, _aliases
    all_names = [canonical, *aliases]

    class _ActionRule(Rule):
        id = rid
        name = f"missing-{canonical}-action"
        description = f"Missing '{canonical}' action (or alias)"
        default_severity = models.Severity.WARNING

        def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
            action_names = set(context.actions.keys())
            if any(n in action_names for n in all_names):
                return []
            return [
                self.diagnostic(
                    f"Missing '{canonical}' action (or alias: {', '.join(aliases)})",
                    path="charmcraft.yaml",
                    fix_hint=f"Add a '{canonical}' action to charmcraft.yaml",
                )
            ]

    _ActionRule.__name__ = f"ActionRule_{rid}"
    _ActionRule.__qualname__ = _ActionRule.__name__
    return _ActionRule


for _rid, (_canonical, _aliases) in _EXPECTED_ACTIONS.items():
    _make_action_rule(_rid, _canonical, _aliases)


class ActionMissingDescription(Rule):
    """Check that all actions have descriptions."""

    id = "ACT004"
    name = "action-missing-description"
    description = "Action is missing a description"
    default_severity = models.Severity.WARNING

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        for action_name, action_def in context.actions.items():
            if not isinstance(action_def, dict):
                continue
            if not action_def.get("description"):
                diagnostics.append(
                    self.diagnostic(
                        f"Action '{action_name}' is missing a description",
                        path="charmcraft.yaml",
                    )
                )
        return diagnostics


class ActionParamMissingDescription(Rule):
    """Check that all action parameters have descriptions."""

    id = "ACT005"
    name = "action-param-missing-description"
    description = "Action parameter is missing a description"
    default_severity = models.Severity.INFO

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        for action_name, action_def in context.actions.items():
            if not isinstance(action_def, dict):
                continue
            params: dict[str, Any] = action_def.get("params", action_def.get("parameters", {}))
            if not isinstance(params, dict):
                continue
            properties = params.get("properties", params)
            for param_name, param_def in properties.items():
                if isinstance(param_def, dict) and not param_def.get("description"):
                    diagnostics.append(
                        self.diagnostic(
                            f"Action '{action_name}' parameter '{param_name}' "
                            f"is missing a description",
                            path="charmcraft.yaml",
                        )
                    )
        return diagnostics


# AST helpers shared by ACT006 / ACT007 — landed ahead of those rules
# so each rule's own PR shows just the rule class.


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
