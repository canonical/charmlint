"""JUJU rules — Juju-ness / idiomatic ops conventions."""

import ast

from .. import models
from . import Rule

_STATUS_NAMES = frozenset({"ActiveStatus", "WaitingStatus", "BlockedStatus"})


def _is_unit_status_target(target: ast.expr) -> bool:
    """True if ``target`` is ``self.unit.status`` or ``self.model.unit.status``."""
    if not isinstance(target, ast.Attribute) or target.attr != "status":
        return False
    inner = target.value
    if not (isinstance(inner, ast.Attribute) and inner.attr == "unit"):
        return False
    # self.unit.status
    base = inner.value
    if isinstance(base, ast.Name) and base.id == "self":
        return True
    # self.model.unit.status
    return (
        isinstance(base, ast.Attribute)
        and base.attr == "model"
        and isinstance(base.value, ast.Name)
        and base.value.id == "self"
    )


def _status_call_name(value: ast.expr) -> str | None:
    """Return ``Xxx`` if ``value`` is ``XxxStatus(...)`` or ``ops.XxxStatus(...)``."""
    if not isinstance(value, ast.Call):
        return None
    func = value.func
    if isinstance(func, ast.Name):
        name = func.id
    elif isinstance(func, ast.Attribute):
        name = func.attr
    else:
        return None
    if name in _STATUS_NAMES:
        return name
    return None


def _find_status_assignments(
    tree: ast.AST,
) -> list[tuple[ast.Assign, str | None, str]]:
    """Return ``(assign_node, enclosing_func_name, status_name)`` triples.

    ``enclosing_func_name`` is ``None`` for assignments at module/class scope.
    """
    results: list[tuple[ast.Assign, str | None, str]] = []
    parent_func: dict[int, str] = {}

    def walk(node: ast.AST, func: str | None) -> None:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            func = node.name
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.Assign):
                parent_func[id(child)] = func or ""
            walk(child, func)

    walk(tree, None)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        status = _status_call_name(node.value)
        if status is None or status == "MaintenanceStatus":
            continue
        if not any(_is_unit_status_target(t) for t in node.targets):
            continue
        func_name = parent_func.get(id(node)) or None
        results.append((node, func_name, status))
    return results


def _observes_collect_unit_status(tree: ast.AST) -> bool:
    """True if any ``self.framework.observe(self.on.collect_unit_status, ...)``
    or equivalent ``observe(self.on.collect_unit_status, ...)`` appears."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (
            (isinstance(func, ast.Attribute) and func.attr == "observe")
            or (isinstance(func, ast.Name) and func.id == "observe")
        ):
            continue
        if not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Attribute) and first.attr == "collect_unit_status":
            return True
    return False


class StatusDirectAssignment(Rule):
    """Flag direct ``self.unit.status = XxxStatus(...)`` outside collect_*_status."""

    id = "JUJU001"
    name = "status-direct-assignment"
    description = "Status set via direct assignment outside a collect_*_status handler"
    default_severity = models.Severity.INFO

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        for path, content in context.python_sources.items():
            if "lib" in path.parts:
                continue
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue
            for node, func_name, status in _find_status_assignments(tree):
                if func_name and func_name.startswith("_on_collect_"):
                    continue
                diagnostics.append(
                    self.diagnostic(
                        f"`self.unit.status = {status}(...)` set by direct "
                        "assignment — prefer setting status from a "
                        "`collect_unit_status` handler so Juju reconciles "
                        "competing statuses",
                        path=str(path),
                        line=node.lineno,
                        fix_hint=(
                            "Move the status decision into a "
                            "`_on_collect_unit_status` handler and `event.add_status(...)`"
                        ),
                    )
                )
        return diagnostics


class StatusMixedPatterns(Rule):
    """Flag charms that observe collect_unit_status AND also assign status directly."""

    id = "JUJU007"
    name = "status-mixed-patterns"
    description = "Charm uses both collect_unit_status and direct status assignment"
    default_severity = models.Severity.WARNING

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        observes = False
        direct_assignments: list[tuple[str, int]] = []
        for path, content in context.python_sources.items():
            if "lib" in path.parts:
                continue
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue
            if _observes_collect_unit_status(tree):
                observes = True
            for node, func_name, _status in _find_status_assignments(tree):
                if func_name and func_name.startswith("_on_collect_"):
                    continue
                direct_assignments.append((str(path), node.lineno))
        if not (observes and direct_assignments):
            return []
        path, line = direct_assignments[0]
        return [
            self.diagnostic(
                "Charm observes `collect_unit_status` but also sets "
                "`self.unit.status` directly elsewhere — pick one pattern; "
                "mixing them makes the final status order-dependent",
                path=path,
                line=line,
                fix_hint=(
                    "Remove direct `self.unit.status = ...` assignments and "
                    "decide status only inside the `collect_unit_status` handler"
                ),
            )
        ]
