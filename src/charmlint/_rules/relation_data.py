"""Relation-data hygiene rules.

Module shell + shared regex/function-walker for REL001 and REL002.
The rule classes follow in their own PRs.
"""

import ast
import pathlib
import re

from .. import _models as models  # noqa: F401  # used by the rule PRs that follow
from . import Rule  # noqa: F401  # used by the rule PRs that follow

# Direct subscript reads that can raise on None app/unit.
_READ_APP_SUBSCRIPT = re.compile(r"\.relation\.data\[\s*event\.app\s*\]")
_READ_UNIT_SUBSCRIPT = re.compile(r"\.relation\.data\[\s*event\.unit\s*\]")

# Either form of guard for the bare ``event.app`` / ``event.unit``.
_APP_GUARD = re.compile(
    r"event\.app\s+is(?:\s+not)?\s+None"
    r"|if\s+(?:not\s+)?event\.app\b"
    r"|\.data\.get\(\s*event\.app"
)
_UNIT_GUARD = re.compile(
    r"event\.unit\s+is(?:\s+not)?\s+None"
    r"|if\s+(?:not\s+)?event\.unit\b"
    r"|\.data\.get\(\s*event\.unit"
)

# Writes to the *own* app data bag — `[self.app]` indexed and assigned to.
_WRITE_SELF_APP = re.compile(r"\.relation\.data\[\s*self\.app\s*\]\s*\[")
_LEADER_GUARD = re.compile(r"is_leader\s*\(")


def _function_segments(
    sources: dict[pathlib.Path, str],
) -> list[tuple[pathlib.Path, ast.FunctionDef, str]]:
    """Return ``(path, FunctionDef, source-text)`` for every function in src/."""
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
