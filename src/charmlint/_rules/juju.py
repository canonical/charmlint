"""JUJU rules — Juju-ness / idiomatic ops conventions."""

import ast

from .. import models
from . import Rule

_MULTI_ROLE_OPTION_KEYS = {"role", "mode", "type"}


def _is_multi_role(metadata: dict) -> bool:
    """Heuristic: charm has a role/mode/type config option or a non-empty peers section."""
    config = metadata.get("config")
    if isinstance(config, dict):
        options = config.get("options")
        if isinstance(options, dict) and any(key in options for key in _MULTI_ROLE_OPTION_KEYS):
            return True
    peers = metadata.get("peers")
    return bool(isinstance(peers, dict) and peers)


def _is_active_status_call(call: ast.Call) -> bool:
    """Return True if ``call`` invokes ``ActiveStatus`` (bare Name or qualified Attribute)."""
    func = call.func
    if isinstance(func, ast.Name) and func.id == "ActiveStatus":
        return True
    return isinstance(func, ast.Attribute) and func.attr == "ActiveStatus"


def _is_empty_active_status(call: ast.Call) -> bool:
    """Return True if ``call`` has no positional args or a single empty-string arg."""
    if call.keywords:
        return False
    if not call.args:
        return True
    if len(call.args) == 1:
        arg = call.args[0]
        if isinstance(arg, ast.Constant) and arg.value == "":
            return True
    return False


class ActiveStatusEmptyMultiRole(Rule):
    """Flag bare ``ActiveStatus()`` in multi-role charms — operators benefit from role context."""

    id = "JUJU004"
    name = "activestatus-empty-multi-role"
    description = "ActiveStatus() with no message in a multi-role charm"
    default_severity = models.Severity.INFO

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        if not _is_multi_role(context.metadata):
            return diagnostics
        for path, content in context.python_sources.items():
            if "lib" in path.parts:
                continue
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if not _is_active_status_call(node):
                    continue
                if not _is_empty_active_status(node):
                    continue
                diagnostics.append(
                    self.diagnostic(
                        "ActiveStatus() called with no message in a multi-role charm — "
                        "include the active role/mode so operators can tell units apart "
                        "in `juju status`",
                        path=str(path),
                        line=node.lineno,
                        fix_hint=(
                            "Pass a message describing the active role, e.g. "
                            '`ActiveStatus(f"role: {self._role}")`'
                        ),
                    )
                )
        return diagnostics
