"""Pebble layer rules.

The ``custom-charm`` skill's K8s subsection recites three Pebble
contracts the agent currently re-derives every turn:

1. ``container.add_layer(name, layer, combine=True)`` — without
   ``combine=True``, repeated calls stack duplicates instead of
   merging.
2. Pebble methods must be guarded by ``container.can_connect()``;
   without the guard a hook can hit ``ConnectionError`` early in
   the unit's lifecycle.
3. Each service entry in a Pebble layer needs ``override``,
   ``command``, and ``startup``.

This module ships the static checks for all three.  The handler
detection is per-function to mirror the relation-data rules; the
service-dict scan walks every dict literal in src/ source so it
catches layers built inline as well as via helper methods.
"""

import ast
import pathlib

from .. import models
from . import Rule

# Pebble methods that need a can_connect guard.
_PEBBLE_CALLS = frozenset({"add_layer", "replan", "restart", "start", "stop", "autostart", "exec"})


def _function_segments(
    sources: dict[pathlib.Path, str],
) -> list[tuple[pathlib.Path, ast.FunctionDef, str]]:
    """Yield ``(path, FunctionDef, source-text)`` for every function in src/."""
    out: list[tuple[pathlib.Path, ast.FunctionDef, str]] = []
    for path, content in sources.items():
        if "lib" in path.parts:
            continue
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                segment = ast.get_source_segment(content, node)
                if segment:
                    out.append((path, node, segment))
    return out


def _string_key(node: ast.expr) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _has_kwarg(call: ast.Call, name: str) -> bool:
    return any(kw.arg == name for kw in call.keywords)


class PebbleAddLayerNoCombine(Rule):
    """Flag ``add_layer(...)`` calls missing ``combine=True``."""

    id = "PEB001"
    name = "pebble-add-layer-no-combine"
    description = "container.add_layer() called without combine=True"
    default_severity = models.Severity.WARNING

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        for path, content in context.python_sources.items():
            if "lib" in path.parts:
                continue
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "add_layer"
                ):
                    continue
                if _has_kwarg(node, "combine"):
                    continue
                diagnostics.append(
                    self.diagnostic(
                        "add_layer() called without combine=True — repeated calls "
                        "stack duplicate layers instead of merging",
                        path=str(path),
                        line=node.lineno,
                        fix_hint="Pass `combine=True` so calls merge into the existing layer",
                    )
                )
        return diagnostics


class PebbleCallWithoutCanConnect(Rule):
    """Flag Pebble methods called in a function without can_connect guard."""

    id = "PEB002"
    name = "pebble-call-without-can-connect"
    description = "Pebble method called in a function with no can_connect() guard"
    default_severity = models.Severity.WARNING

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        for path, func, source in _function_segments(context.python_sources):
            if "can_connect" in source:
                continue
            # The pebble_ready handler is called *because* connect succeeded —
            # the framework has done the guard for us.
            if "pebble_ready" in func.name or "PebbleReady" in source:
                continue
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if not (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in _PEBBLE_CALLS
                ):
                    continue
                diagnostics.append(
                    self.diagnostic(
                        f"Function '{func.name}' calls .{node.func.attr}() with no "
                        "can_connect() guard — early hooks may raise ConnectionError",
                        path=str(path),
                        line=func.lineno,
                        fix_hint=(
                            "Add `if not container.can_connect(): event.defer(); return` "
                            "or hoist the call into the pebble_ready handler"
                        ),
                    )
                )
                break  # One diagnostic per function is enough.
        return diagnostics


def _service_dict_keys(service_node: ast.expr) -> set[str] | None:
    """Return the string-keyed entries of an AST Dict, else ``None``."""
    if not isinstance(service_node, ast.Dict):
        return None
    keys: set[str] = set()
    for key_node in service_node.keys:
        if key_node is None:
            continue
        key = _string_key(key_node)
        if key is not None:
            keys.add(key)
    return keys


def _iter_service_entries(dict_node: ast.Dict) -> list[tuple[str, ast.expr]]:
    """For a layer Dict that has a ``services`` key, return ``(svc_name, svc_node)``."""
    entries: list[tuple[str, ast.expr]] = []
    for key_node, value_node in zip(dict_node.keys, dict_node.values, strict=False):
        if key_node is None:
            continue
        if _string_key(key_node) != "services":
            continue
        if not isinstance(value_node, ast.Dict):
            continue
        for svc_key, svc_value in zip(value_node.keys, value_node.values, strict=False):
            if svc_key is None:
                continue
            name = _string_key(svc_key)
            if name is not None:
                entries.append((name, svc_value))
    return entries


_REQUIRED_SERVICE_KEYS = ("override", "command", "startup")


class PebbleLayerServiceMissingKeys(Rule):
    """Flag Pebble layer service dicts missing override/command/startup."""

    id = "PEB003"
    name = "pebble-layer-service-missing-keys"
    description = "Pebble layer service entry missing required key (override/command/startup)"
    default_severity = models.Severity.WARNING

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        for path, content in context.python_sources.items():
            if "lib" in path.parts:
                continue
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Dict):
                    continue
                for svc_name, svc_node in _iter_service_entries(node):
                    keys = _service_dict_keys(svc_node)
                    if keys is None:
                        continue
                    missing = [k for k in _REQUIRED_SERVICE_KEYS if k not in keys]
                    if not missing:
                        continue
                    diagnostics.append(
                        self.diagnostic(
                            f"Pebble service '{svc_name}' is missing required key(s): "
                            f"{', '.join(missing)}",
                            path=str(path),
                            line=svc_node.lineno,
                            fix_hint=(
                                "Pebble services need `override` (replace/merge), "
                                "`command`, and `startup` (enabled/disabled) at minimum"
                            ),
                        )
                    )
        return diagnostics
