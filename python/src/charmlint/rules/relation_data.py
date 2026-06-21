"""Relation-data hygiene rules.

The ``relation-data-design`` skill bakes in two contracts the
agent currently re-derives every turn: relation-data reads via
``event.relation.data[event.app]`` (or ``[event.unit]``) need a
guard for the ``None`` case Juju occasionally hands you, and any
write to ``event.relation.data[self.app]`` must be inside a
``self.unit.is_leader()`` guard.  Both are flow-shape patterns;
this module checks them as per-function regex sweeps, matching the
roadmap's "regex over the relation-event functions" budget rather
than full flow-sensitive analysis.

False-positive risk: a charm that guards its read by routing
through a helper, or one that uses a non-standard parameter name
for the event, will be missed by the read-guard check.  Pre-1.0,
this is an acceptable trade for ~60 LoC of static text matching.
"""

import ast
import pathlib
import re

from .. import models
from . import Rule

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


class RelationDataReadUnguarded(Rule):
    """Flag handlers that subscript ``event.relation.data[event.app/unit]`` unguarded."""

    id = "REL001"
    name = "relation-data-read-unguarded"
    description = "Reads event.relation.data[event.app] or [event.unit] without guarding the key"
    default_severity = models.Severity.WARNING

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        for path, func, source in _function_segments(context.python_sources):
            if _READ_APP_SUBSCRIPT.search(source) and not _APP_GUARD.search(source):
                diagnostics.append(
                    self.diagnostic(
                        f"Handler '{func.name}' reads event.relation.data[event.app] "
                        "without guarding event.app — Juju may set event.app to None "
                        "on some event shapes",
                        path=str(path),
                        line=func.lineno,
                        fix_hint=(
                            "Guard with `if event.app is None: return` or use "
                            "`event.relation.data.get(event.app, {})`"
                        ),
                    )
                )
            if _READ_UNIT_SUBSCRIPT.search(source) and not _UNIT_GUARD.search(source):
                diagnostics.append(
                    self.diagnostic(
                        f"Handler '{func.name}' reads event.relation.data[event.unit] "
                        "without guarding event.unit",
                        path=str(path),
                        line=func.lineno,
                        fix_hint=(
                            "Guard with `if event.unit is None: return` or use "
                            "`event.relation.data.get(event.unit, {})`"
                        ),
                    )
                )
        return diagnostics


class RelationDataWriteWithoutLeader(Rule):
    """Flag handlers that write to ``relation.data[self.app]`` without is_leader guard."""

    id = "REL002"
    name = "relation-data-write-without-leader"
    description = "Writes app-data bag without an is_leader() guard"
    default_severity = models.Severity.WARNING

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        for path, func, source in _function_segments(context.python_sources):
            if not _WRITE_SELF_APP.search(source):
                continue
            if _LEADER_GUARD.search(source):
                continue
            diagnostics.append(
                self.diagnostic(
                    f"Handler '{func.name}' writes to event.relation.data[self.app] "
                    "without an is_leader() guard — non-leader writes raise at runtime",
                    path=str(path),
                    line=func.lineno,
                    fix_hint=("Add `if not self.unit.is_leader(): return` before the write"),
                )
            )
        return diagnostics
