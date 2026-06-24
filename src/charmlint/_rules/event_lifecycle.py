"""Event lifecycle completeness rules (EVNT).

The roadmap groups "did the charm wire up the right reactions to Juju's
lifecycle?" checks under an EVNT lens.  This module currently hosts
EVNT002 — see ``charmlint-rule-proposals.md §3.9``.

EVNT002 flags relation-data reads that subscript a string-literal key
without any schema validation.  ``event.relation.data[event.app]["k"]``
raises ``KeyError`` when the remote side has not yet populated ``k``; a
schema-validated read (pydantic) or a defensive ``.get("k")`` is the
fix.  False-positive risk is high, so detection is deliberately narrow:
only direct subscript on relation data, only where the surrounding
function has no ``try/except KeyError`` and the module imports neither
``pydantic`` package form.
"""

import ast
import pathlib  # noqa: F401  (kept for typing-style clarity in future rules)
import re

from .. import models
from . import Rule

# Subscript reads of the form `<...>.relation.data[<app_or_unit>]["key"]`.
# Allows event.app/event.unit and self.app/self.unit as the bag selector.
_RELATION_DATA_SUBSCRIPT = re.compile(
    r"\.relation\.data\[\s*"
    r"(?:event\.app|event\.unit|self\.app|self\.unit)"
    r"\s*\]\s*\[\s*['\"]\w+['\"]\s*\]"
)


def _module_imports_pydantic(content: str) -> bool:
    """True if the module has any pydantic import at all."""
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return "pydantic" in content
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "pydantic" or alias.name.startswith("pydantic."):
                    return True
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module
            and (node.module == "pydantic" or node.module.startswith("pydantic."))
        ):
            return True
    return False


def _function_has_keyerror_guard(func: ast.FunctionDef) -> bool:
    """True if the function body wraps anything in `try: ... except KeyError`."""
    for node in ast.walk(func):
        if not isinstance(node, ast.Try):
            continue
        for handler in node.handlers:
            exc = handler.type
            if exc is None:
                continue
            names: list[ast.expr] = []
            if isinstance(exc, ast.Tuple):
                names.extend(exc.elts)
            else:
                names.append(exc)
            for name in names:
                if isinstance(name, ast.Name) and name.id == "KeyError":
                    return True
                if isinstance(name, ast.Attribute) and name.attr == "KeyError":
                    return True
    return False


class RelationDataNoStructuredSchema(Rule):
    """Flag unguarded `relation.data[...]["key"]` subscript reads."""

    id = "EVNT002"
    name = "relation-data-no-structured-schema"
    description = (
        "Relation data accessed by string-literal subscript without a schema "
        "(pydantic) or KeyError guard"
    )
    default_severity = models.Severity.INFO

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        for path, content in context.python_sources.items():
            if "lib" in path.parts:
                continue
            if _module_imports_pydantic(content):
                continue
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.FunctionDef):
                    continue
                segment = ast.get_source_segment(content, node)
                if segment is None:
                    continue
                if not _RELATION_DATA_SUBSCRIPT.search(segment):
                    continue
                if _function_has_keyerror_guard(node):
                    continue
                diagnostics.append(
                    self.diagnostic(
                        f"Handler '{node.name}' reads relation data via "
                        "string-literal subscript without schema validation "
                        "— a missing key will raise KeyError at runtime",
                        path=str(path),
                        line=node.lineno,
                        fix_hint=(
                            'Use `.get("key")` with a default, wrap the '
                            "access in `try/except KeyError`, or validate "
                            "the databag with pydantic before reading"
                        ),
                    )
                )
        return diagnostics
