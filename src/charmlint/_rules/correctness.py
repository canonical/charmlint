"""Correctness rules — runtime-correctness issues in charm source."""

import ast

from .. import models
from . import Rule

# Logger-style method names whose presence in an except-block is treated as
# evidence that the exception was at least observed (not silently swallowed).
_LOGGER_METHODS: frozenset[str] = frozenset(
    {"debug", "info", "warning", "error", "critical", "exception"},
)


def _is_bare_exception_handler(handler: ast.ExceptHandler) -> bool:
    """True if ``handler`` catches exactly ``Exception`` (not a subclass tuple)."""
    return isinstance(handler.type, ast.Name) and handler.type.id == "Exception"


def _handler_body_acknowledges(handler: ast.ExceptHandler) -> bool:
    """True if the handler's body contains a logger call or a ``raise``.

    ``raise`` covers both bare re-raise and ``raise SomeOtherError(...) from e``;
    either way the exception is not silently swallowed.  A logger call is any
    ``Call`` whose ``func.attr`` is one of the standard logging method names —
    the receiver isn't inspected because charms wrap loggers in many ways
    (``logger``, ``self.logger``, ``log``, module-level loggers from a helper).
    """
    for node in ast.walk(handler):
        if isinstance(node, ast.Raise):
            return True
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _LOGGER_METHODS
        ):
            return True
    return False


class ExceptExceptionSwallowed(Rule):
    """Flag ``except Exception:`` blocks that neither log nor re-raise."""

    id = "CORR005"
    name = "except-exception-swallowed"
    description = "except Exception block swallows the error without logging or re-raising"
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
                if not isinstance(node, ast.ExceptHandler):
                    continue
                if not _is_bare_exception_handler(node):
                    continue
                if _handler_body_acknowledges(node):
                    continue
                diagnostics.append(
                    self.diagnostic(
                        "`except Exception:` block silently swallows the error — "
                        "the hook reports success to Juju while an error occurred",
                        path=str(path),
                        line=node.lineno,
                        fix_hint=(
                            "Log the exception (e.g. `logger.exception(...)`) or "
                            "re-raise it; catch a more specific exception type if "
                            "the failure mode is known"
                        ),
                    )
                )
        return diagnostics
