"""JUJU rules — Juju-ness / idiomatic ops conventions."""

import pathlib
import re

from .. import _models as models
from ._base import Rule

_OPS_DEP_RE = re.compile(
    r"""
    ^\s*
    ops                     # the distribution name
    (?:\s*\[[^\]]*\])?      # optional [extras], e.g. ops[tracing]
    \s*
    (?P<spec>[^#;]*)        # everything up to a comment or PEP 508 marker
    """,
    re.IGNORECASE | re.VERBOSE,
)

_QUOTED_RE = re.compile(r"""(['"])([^'"]*)\1""")


def _iter_dep_lines(charm_dir: pathlib.Path) -> list[tuple[str, str]]:
    """Return ``(source_path, raw_line)`` for every dependency-looking line.

    Quoted strings are pulled from ``pyproject.toml`` and bare lines
    from ``requirements.txt``. No TOML/PEP-508 parsing is attempted —
    the rules only need to spot the ``ops`` name and what immediately
    follows it.
    """
    lines: list[tuple[str, str]] = []

    pyproject = charm_dir / "pyproject.toml"
    if pyproject.is_file():
        try:
            text = pyproject.read_text()
        except OSError:
            text = ""
        for match in _QUOTED_RE.finditer(text):
            inner = match.group(2)
            if inner:
                lines.append((str(pyproject), inner))

    requirements = charm_dir / "requirements.txt"
    if requirements.is_file():
        try:
            text = requirements.read_text()
        except OSError:
            text = ""
        for raw in text.splitlines():
            stripped = raw.split("#", 1)[0].strip()
            if stripped and not stripped.startswith("-"):
                lines.append((str(requirements), stripped))

    return lines


def _classify_ops_spec(spec: str) -> str | None:
    """Return ``"unpinned"``, ``"exact"``, or ``None`` for an ``ops`` spec."""
    s = spec.strip()
    if not s:
        return "unpinned"
    if s.startswith("=="):
        return "exact"
    return None


class OpsDependencyUnpinned(Rule):
    """Flag an ``ops`` dependency with no version specifier."""

    category = "JUJU"
    number = 3
    name = "ops-dependency-unpinned"
    description = "ops dependency has no version specifier"
    default_severity = models.Severity.WARNING

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        for source, line in _iter_dep_lines(context.charm_dir):
            match = _OPS_DEP_RE.match(line)
            if match is None:
                continue
            if _classify_ops_spec(match.group("spec")) != "unpinned":
                continue
            diagnostics.append(
                self.diagnostic(
                    "ops dependency has no version specifier — "
                    "charms should pin a supported range so dependency "
                    "resolvers do not silently pull a major bump",
                    path=source,
                    fix_hint="Add a version range, e.g. `ops>=2.17,<4`",
                )
            )
        return diagnostics


class OpsDependencyExactlyPinned(Rule):
    """Flag an ``ops`` dependency pinned with ``==``."""

    category = "JUJU"
    number = 4
    name = "ops-dependency-exactly-pinned"
    description = "ops dependency pinned with `==`"
    default_severity = models.Severity.INFO

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        for source, line in _iter_dep_lines(context.charm_dir):
            match = _OPS_DEP_RE.match(line)
            if match is None:
                continue
            if _classify_ops_spec(match.group("spec")) != "exact":
                continue
            diagnostics.append(
                self.diagnostic(
                    "ops dependency is exactly pinned (`==`) — "
                    "prefer a version range so security fixes flow in "
                    "without a manual bump",
                    path=source,
                    fix_hint="Replace the `==` pin with a range, e.g. `ops>=2.17,<4`",
                )
            )
        return diagnostics
