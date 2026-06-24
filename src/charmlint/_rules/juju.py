"""JUJU rules — Juju-ness / idiomatic ops conventions."""

import ast

from .. import models
from . import Rule

_LOGGER_LEVELS = frozenset({"debug", "info", "warning", "error", "critical", "exception"})


def _is_logger_level_call(call: ast.Call) -> bool:
    """True if ``call`` is ``logger.<level>(...)``."""
    func = call.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr in _LOGGER_LEVELS
        and isinstance(func.value, ast.Name)
        and func.value.id == "logger"
    )


class FStringInLoggerCall(Rule):
    """Flag ``logger.<level>(f"...")`` calls — defeats lazy log formatting."""

    id = "JUJU009"
    name = "fstring-in-logger-call"
    description = "f-string passed as the message to a logger.<level>() call"
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
                if not (isinstance(node, ast.Call) and _is_logger_level_call(node)):
                    continue
                if not node.args:
                    continue
                if not isinstance(node.args[0], ast.JoinedStr):
                    continue
                diagnostics.append(
                    self.diagnostic(
                        "f-string passed to logger call — the string is "
                        "formatted even when the log level is disabled, and "
                        "log aggregators cannot group messages by template",
                        path=str(path),
                        line=node.lineno,
                        fix_hint=('Use lazy `%s` formatting: logger.info("value is %s", value)'),
                    )
                )
        return diagnostics
