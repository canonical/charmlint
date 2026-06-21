"""Action rules — expected operational actions and action quality."""

import ast
import pathlib
from typing import Any

from .. import models
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
    """Yield ``(action_name_underscored, handler_method_or_None)`` per observe call.

    Looks for ``<...>.observe(<...>.on.<event>_action, self.<handler>)`` —
    the canonical registration shape in ops charms.  Subscript-style
    (``self.on['my-action']``) and non-self handler targets are
    deliberately ignored; ACT006 only flags the missing-observer case
    when the canonical pattern is absent.
    """
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


def _handler_terminates(handler: ast.FunctionDef) -> bool:
    """True iff handler body calls ``*.set_results(...)`` or ``*.fail(...)``."""
    for sub in ast.walk(handler):
        if (
            isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Attribute)
            and sub.func.attr in ("set_results", "fail")
        ):
            return True
    return False


def _gather_action_observers(
    sources: dict[pathlib.Path, str],
) -> dict[str, tuple[str | None, ast.FunctionDef | None, pathlib.Path]]:
    """Return ``{action: (handler_name, handler_node, source_path)}`` for charm sources.

    Skips ``lib/`` because charm libraries do not register a charm's
    own action observers.  Files that fail to parse are silently
    skipped — charmlint is not a syntax checker, and a partial
    survey is more useful than no survey.
    """
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
    """Check that every declared action has a ``framework.observe`` registration."""

    id = "ACT006"
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


class ActionHandlerIncomplete(Rule):
    """Check that each action handler ends in ``set_results()`` or ``fail()``."""

    id = "ACT007"
    name = "action-handler-incomplete"
    description = "Action handler does not call set_results() or fail()"
    default_severity = models.Severity.WARNING

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        if not context.actions:
            return []
        observers = _gather_action_observers(context.python_sources)
        diagnostics: list[models.Diagnostic] = []
        for action_name in context.actions:
            normalised = action_name.replace("-", "_")
            entry = observers.get(normalised)
            if entry is None:
                # ACT006 will flag the missing-observer case.
                continue
            handler_name, handler_node, path = entry
            if handler_node is None:
                # Observer registered with a non-self target (e.g. delegated
                # to a sub-object) — we cannot resolve the body, so we
                # skip rather than risk a false positive.
                continue
            if _handler_terminates(handler_node):
                continue
            diagnostics.append(
                self.diagnostic(
                    f"Action handler '{handler_name}' for action '{action_name}' "
                    "never calls set_results() or fail() — the action will hang "
                    "until it times out",
                    path=str(path),
                    line=handler_node.lineno,
                    fix_hint=(
                        "Call `event.set_results(...)` on success or "
                        "`event.fail('reason')` to report failure"
                    ),
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
