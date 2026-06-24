"""JUJU rules — Juju-ness / idiomatic ops conventions."""

import ast
import pathlib

from .. import models
from . import Rule


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


def _collect_app_status_handlers(
    sources: dict[pathlib.Path, str],
) -> set[str]:
    """Return handler method names observed for ``collect_app_status``.

    Detects ``self.framework.observe(self.on.collect_app_status, self.<handler>)``
    and the shorter ``self.observe(...)`` form.
    """
    handlers: set[str] = set()
    for path, content in sources.items():
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
                and node.func.attr == "observe"
                and len(node.args) >= 2
            ):
                continue
            event_arg, handler_arg = node.args[0], node.args[1]
            if not (
                isinstance(event_arg, ast.Attribute) and event_arg.attr == "collect_app_status"
            ):
                continue
            if (
                isinstance(handler_arg, ast.Attribute)
                and isinstance(handler_arg.value, ast.Name)
                and handler_arg.value.id == "self"
            ):
                handlers.add(handler_arg.attr)
    return handlers


def _mutates_app_status(func: ast.FunctionDef) -> bool:
    """Return True if ``func`` calls ``event.add_status(...)`` or writes ``self.app.status``."""
    for node in ast.walk(func):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_status"
        ):
            return True
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Attribute)
                    and target.attr == "status"
                    and isinstance(target.value, ast.Attribute)
                    and target.value.attr == "app"
                    and isinstance(target.value.value, ast.Name)
                    and target.value.value.id == "self"
                ):
                    return True
    return False


class CollectAppStatusNoLeaderGuard(Rule):
    """Flag ``collect_app_status`` handlers that mutate app status without ``is_leader()``."""

    id = "JUJU005"
    name = "collect-app-status-no-leader-guard"
    description = (
        "collect_app_status handler mutates application status without an is_leader() guard"
    )
    default_severity = models.Severity.ERROR

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        handler_names = _collect_app_status_handlers(context.python_sources)
        if not handler_names:
            return []
        diagnostics: list[models.Diagnostic] = []
        for path, func, source in _function_segments(context.python_sources):
            if func.name not in handler_names:
                continue
            if not _mutates_app_status(func):
                continue
            if "is_leader(" in source:
                continue
            diagnostics.append(
                self.diagnostic(
                    f"Function '{func.name}' is a collect_app_status handler that "
                    "mutates application status without an is_leader() guard — "
                    "only the leader unit should set application status",
                    path=str(path),
                    line=func.lineno,
                    fix_hint=(
                        "Guard the status mutation with "
                        "`if not self.unit.is_leader(): return` at the top of the handler"
                    ),
                )
            )
        return diagnostics
