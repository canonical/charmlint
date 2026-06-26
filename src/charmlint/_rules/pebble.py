"""Pebble layer rules.

Module shell + AST helpers for PEB001/PEB002/PEB003. The rule classes
follow in their own PRs.
"""

import ast
import pathlib

from .. import _models as models
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


def _called_self_methods(func: ast.FunctionDef) -> set[str]:
    """Return the set of ``self.<name>(...)`` methods invoked in ``func``."""
    called: set[str] = set()
    for node in ast.walk(func):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "self"
        ):
            called.add(node.func.attr)
    return called


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
        segments = _function_segments(context.python_sources)

        guarded: dict[str, bool] = {}
        for _path, func, source in segments:
            if "can_connect" in source or "pebble_ready" in func.name or "PebbleReady" in source:
                guarded[func.name] = True
            else:
                guarded.setdefault(func.name, False)

        callers: dict[str, list[str]] = {}
        for _path, func, _source in segments:
            for callee in _called_self_methods(func):
                callers.setdefault(callee, []).append(func.name)

        changed = True
        while changed:
            changed = False
            for fname, is_guarded in list(guarded.items()):
                if is_guarded:
                    continue
                call_sites = callers.get(fname)
                if not call_sites:
                    continue
                if all(guarded.get(c, False) for c in call_sites):
                    guarded[fname] = True
                    changed = True

        diagnostics: list[models.Diagnostic] = []
        for path, func, source in segments:
            if guarded.get(func.name):
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
                break
        return diagnostics
