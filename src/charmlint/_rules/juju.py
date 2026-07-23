"""JUJU rules — Juju-ness / idiomatic ops conventions."""

import functools
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


def _iter_candidate_lines(charm_dir: pathlib.Path):
    """Yield ``(source_path, raw_line)`` for every dependency-looking line.

    Quoted strings are pulled from ``pyproject.toml`` and bare lines
    from ``requirements.txt``. No TOML/PEP-508 parsing is attempted —
    the rules only need to spot the ``ops`` name and what immediately
    follows it.
    """
    pyproject = charm_dir / "pyproject.toml"
    if pyproject.is_file():
        try:
            text = pyproject.read_text()
        except OSError:
            text = ""
        for match in _QUOTED_RE.finditer(text):
            inner = match.group(2)
            if inner:
                yield str(pyproject), inner

    requirements = charm_dir / "requirements.txt"
    if requirements.is_file():
        try:
            text = requirements.read_text()
        except OSError:
            text = ""
        for raw in text.splitlines():
            stripped = raw.split("#", 1)[0].strip()
            if stripped and not stripped.startswith("-"):
                yield str(requirements), stripped


@functools.cache
def _find_ops_dep(charm_dir: pathlib.Path) -> tuple[str, str] | None:
    """Return ``(source, kind)`` for the first ``ops`` dep found, or ``None``.

    ``kind`` is ``"unpinned"`` if no version specifier is present,
    ``"exact"`` if pinned with ``==``, or ``"ok"`` for anything else
    (range, ``>=``, etc.). Both JUJU rules share this scan so we walk
    the files once per lint and stop at the first hit — a charm should
    only declare ``ops`` in one place.
    """
    for source, line in _iter_candidate_lines(charm_dir):
        match = _OPS_DEP_RE.match(line)
        if match is None:
            continue
        spec = match.group("spec").strip()
        if not spec:
            return source, "unpinned"
        if spec.startswith("=="):
            return source, "exact"
        return source, "ok"
    return None


class OpsDependencyUnpinned(Rule):
    """Flag an ``ops`` dependency with no version specifier."""

    category = "JUJU"
    number = 3
    name = "ops-dependency-unpinned"
    description = "ops dependency has no version specifier"
    default_severity = models.Severity.WARNING

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        found = _find_ops_dep(context.charm_dir)
        if found is None or found[1] != "unpinned":
            return []
        return [
            self.diagnostic(
                "ops dependency has no version specifier — "
                "charms should pin a supported range so dependency "
                "resolvers do not silently pull a major bump",
                path=found[0],
                fix_hint="Add a version range, e.g. `ops>=2.17,<4`",
            )
        ]


class OpsDependencyExactlyPinned(Rule):
    """Flag an ``ops`` dependency pinned with ``==``."""

    category = "JUJU"
    number = 4
    name = "ops-dependency-exactly-pinned"
    description = "ops dependency pinned with `==`"
    default_severity = models.Severity.INFO

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        found = _find_ops_dep(context.charm_dir)
        if found is None or found[1] != "exact":
            return []
        return [
            self.diagnostic(
                "ops dependency is exactly pinned (`==`) — "
                "prefer a version range so security fixes flow in "
                "without a manual bump",
                path=found[0],
                fix_hint="Replace the `==` pin with a range, e.g. `ops>=2.17,<4`",
            )
        ]
