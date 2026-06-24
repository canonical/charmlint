"""Correctness rules — runtime-correctness issues in charm source."""

import ast

from .. import models
from . import Rule


def _is_subprocess_run(call: ast.Call) -> bool:
    """True if ``call`` is a ``subprocess.run(...)`` invocation."""
    func = call.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "run"
        and isinstance(func.value, ast.Name)
        and func.value.id == "subprocess"
    )


def _has_keyword_true(call: ast.Call, name: str) -> bool:
    for kw in call.keywords:
        if kw.arg == name and isinstance(kw.value, ast.Constant) and kw.value.value is True:
            return True
    return False


def _result_returncode_checked(tree: ast.AST, call: ast.Call) -> bool:
    """True if ``call``'s result is bound to a name and ``<name>.returncode`` is read."""
    target_name: str | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and node.value is call:
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    target_name = tgt.id
                    break
            break
    if target_name is None:
        return False
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "returncode"
            and isinstance(node.value, ast.Name)
            and node.value.id == target_name
        ):
            return True
    return False


def _is_super_init_call(stmt: ast.stmt) -> bool:
    """True if ``stmt`` is an expression statement calling ``super().__init__(...)``."""
    if not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Call):
        return False
    call = stmt.value
    func = call.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "__init__"
        and isinstance(func.value, ast.Call)
        and isinstance(func.value.func, ast.Name)
        and func.value.func.id == "super"
    )


def _is_framework_observe_call(stmt: ast.stmt) -> bool:
    """True if ``stmt`` is an expression statement calling ``self.framework.observe(...)``."""
    if not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Call):
        return False
    func = stmt.value.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "observe"
        and isinstance(func.value, ast.Attribute)
        and func.value.attr == "framework"
        and isinstance(func.value.value, ast.Name)
        and func.value.value.id == "self"
    )


def _is_self_attr_target(target: ast.expr) -> bool:
    return (
        isinstance(target, ast.Attribute)
        and isinstance(target.value, ast.Name)
        and target.value.id == "self"
    )


def _is_helper_assignment(stmt: ast.stmt) -> bool:
    """True if ``stmt`` is ``self.x = <Call>`` or ``self.x: T = <Call>`` — helper construction."""
    if isinstance(stmt, ast.Assign):
        if not all(_is_self_attr_target(t) for t in stmt.targets):
            return False
        return isinstance(stmt.value, ast.Call)
    if isinstance(stmt, ast.AnnAssign):
        if not _is_self_attr_target(stmt.target):
            return False
        return stmt.value is not None and isinstance(stmt.value, ast.Call)
    return False


def _is_docstring(stmt: ast.stmt) -> bool:
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and isinstance(stmt.value.value, str)
    )


def _inherits_charmbase(cls: ast.ClassDef) -> bool:
    """True if ``cls`` directly inherits from ``ops.CharmBase`` or ``CharmBase``."""
    for base in cls.bases:
        if isinstance(base, ast.Name) and base.id == "CharmBase":
            return True
        if (
            isinstance(base, ast.Attribute)
            and base.attr == "CharmBase"
            and isinstance(base.value, ast.Name)
            and base.value.id == "ops"
        ):
            return True
    return False


class SubprocessRunWithoutCheck(Rule):
    """Flag ``subprocess.run(...)`` calls without ``check=True`` or returncode inspection."""

    id = "CORR001"
    name = "subprocess-run-without-check"
    description = "subprocess.run() called without check=True or returncode inspection"
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
                if not (isinstance(node, ast.Call) and _is_subprocess_run(node)):
                    continue
                if _has_keyword_true(node, "check"):
                    continue
                if _result_returncode_checked(tree, node):
                    continue
                diagnostics.append(
                    self.diagnostic(
                        "subprocess.run() called without check=True — a non-zero exit "
                        "is silently ignored and the hook continues as if it succeeded",
                        path=str(path),
                        line=node.lineno,
                        fix_hint=(
                            "Pass `check=True` so the call raises on failure, or "
                            "inspect `.returncode` on the returned CompletedProcess"
                        ),
                    )
                )
        return diagnostics


class SideEffectsInCharmInit(Rule):
    """Flag side-effecting statements in a ``CharmBase.__init__`` body."""

    id = "CORR007"
    name = "side-effects-in-charm-init"
    description = (
        "CharmBase.__init__ should only call super().__init__(), observe events, "
        "and construct helper objects"
    )
    default_severity = models.Severity.ERROR

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
                if not (isinstance(node, ast.ClassDef) and _inherits_charmbase(node)):
                    continue
                for item in node.body:
                    if not (isinstance(item, ast.FunctionDef) and item.name == "__init__"):
                        continue
                    for stmt in item.body:
                        if (
                            _is_docstring(stmt)
                            or isinstance(stmt, ast.Pass)
                            or _is_super_init_call(stmt)
                            or _is_framework_observe_call(stmt)
                            or _is_helper_assignment(stmt)
                        ):
                            continue
                        diagnostics.append(
                            self.diagnostic(
                                "CharmBase.__init__ contains a side-effecting statement — "
                                "__init__ should only call super().__init__(), observe events, "
                                "and construct helper objects",
                                path=str(path),
                                line=stmt.lineno,
                                fix_hint=(
                                    "Move I/O, status updates, config reads, and workload "
                                    "calls into an event handler (e.g. _on_install, "
                                    "_on_config_changed)"
                                ),
                            )
                        )
        return diagnostics
