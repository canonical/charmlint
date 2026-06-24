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
