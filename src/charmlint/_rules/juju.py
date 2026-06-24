"""JUJU rules — Juju-ness / idiomatic ops conventions."""

import ast

from .. import models
from . import Rule

_SECRET_READ_METHODS = frozenset({"get_content", "peek_content"})
_SUBPROCESS_FUNCS = frozenset({"run", "Popen"})


def _reads_secret_content(func: ast.FunctionDef) -> bool:
    """True if the function body invokes ``.get_content()`` or ``.peek_content()``."""
    for node in ast.walk(func):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _SECRET_READ_METHODS
        ):
            return True
    return False


def _subprocess_call_with_variable_list(func: ast.FunctionDef) -> ast.Call | None:
    """Return a ``subprocess.run([...])`` / ``Popen([...])`` call whose list has a
    non-string-literal element, or ``None``."""
    for node in ast.walk(func):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _SUBPROCESS_FUNCS
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "subprocess"
        ):
            continue
        if not node.args:
            continue
        first = node.args[0]
        if not isinstance(first, ast.List):
            continue
        for elt in first.elts:
            if not (isinstance(elt, ast.Constant) and isinstance(elt.value, str)):
                return node
    return None


class SecretAsSubprocessArg(Rule):
    """Flag passing Juju secret content as a subprocess CLI argument."""

    id = "JUJU010"
    name = "secret-as-subprocess-arg"
    description = (
        "Juju secret content passed as a subprocess CLI argument — "
        "argv is visible in /proc and process listings"
    )
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
            for node in ast.walk(tree):
                if not isinstance(node, ast.FunctionDef):
                    continue
                if not _reads_secret_content(node):
                    continue
                if _subprocess_call_with_variable_list(node) is None:
                    continue
                diagnostics.append(
                    self.diagnostic(
                        f"Function '{node.name}' reads Juju secret content and "
                        "constructs a subprocess.run/Popen list containing a "
                        "non-literal element — the secret may end up on argv, "
                        "which is visible via /proc and `ps`",
                        path=str(path),
                        line=node.lineno,
                        fix_hint=(
                            "Pass the secret via stdin (Popen(..., stdin=PIPE)), "
                            "an environment variable, or a file rather than as a "
                            "command-line argument"
                        ),
                    )
                )
        return diagnostics
