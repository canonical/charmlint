"""JUJU rules — Juju-ness / idiomatic ops conventions."""

import functools
import pathlib
import re
from typing import Any

from .. import _models as models
from ._base import Rule

_PEP508_RE = re.compile(
    r"""
    ^\s*
    (?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)   # the distribution name
    \s*
    (?:\[[^\]]*\])?                        # optional [extras], e.g. ops[tracing]
    \s*
    (?P<rest>.*)                           # the version specifier and/or a PEP 508 marker
    """,
    re.VERBOSE | re.DOTALL,
)


def _normalize(name: str) -> str:
    """PEP 503 name normalisation — dashes/underscores/dots collapse and lowercase."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _classify_spec(spec: str) -> str:
    """Return ``"unpinned"`` / ``"exact"`` / ``"ok"`` for a version specifier."""
    s = spec.strip()
    if not s or s == "*":
        return "unpinned"
    if s.startswith("=="):
        return "exact"
    return "ok"


def _classify_pep508(entry: str) -> str | None:
    """Classify a PEP 508 requirement string, returning ``None`` if it isn't ``ops``."""
    match = _PEP508_RE.match(entry)
    if match is None:
        return None
    if _normalize(match.group("name")) != "ops":
        return None
    spec = match.group("rest").split(";", 1)[0].strip()
    return _classify_spec(spec)


def _classify_poetry(value: Any) -> str:
    """Classify a Poetry dependency value (bare string, or table with ``version``)."""
    spec = str(value.get("version", "")) if isinstance(value, dict) else str(value)
    return _classify_spec(spec)


def _walk_pep508_list(entries: Any):
    """Yield PEP 508 strings from a value that should be a list of requirements."""
    if not isinstance(entries, list):
        return
    for entry in entries:
        if isinstance(entry, str):
            yield entry


def _find_ops_in_pyproject(data: dict[str, Any]) -> tuple[str, str, int | None] | None:
    """Look for an ``ops`` dependency across the common pyproject.toml layouts.

    *data* is the charm's parsed ``pyproject.toml``, read once by the
    linter core. Returns ``(source, kind, line)`` where ``kind`` is
    ``"unpinned"`` / ``"exact"`` / ``"ok"`` and ``line`` is always
    ``None`` — ``tomllib`` discards positions, so a finding here
    anchors to the file. ``None`` means no ``ops`` dependency appears
    in any known location.
    """
    source = "pyproject.toml"

    # PEP 621 — [project.dependencies] and [project.optional-dependencies.*]
    project = data.get("project")
    if isinstance(project, dict):
        for entry in _walk_pep508_list(project.get("dependencies")):
            kind = _classify_pep508(entry)
            if kind is not None:
                return source, kind, None
        optional = project.get("optional-dependencies")
        if isinstance(optional, dict):
            for entries in optional.values():
                for entry in _walk_pep508_list(entries):
                    kind = _classify_pep508(entry)
                    if kind is not None:
                        return source, kind, None

    # PEP 735 — [dependency-groups.*]
    groups = data.get("dependency-groups")
    if isinstance(groups, dict):
        for entries in groups.values():
            for entry in _walk_pep508_list(entries):
                kind = _classify_pep508(entry)
                if kind is not None:
                    return source, kind, None

    # Poetry — [tool.poetry.dependencies], legacy [tool.poetry.dev-dependencies],
    # and [tool.poetry.group.<name>.dependencies].
    tool = data.get("tool")
    if isinstance(tool, dict):
        poetry = tool.get("poetry")
        if isinstance(poetry, dict):
            for key in ("dependencies", "dev-dependencies"):
                deps = poetry.get(key)
                if isinstance(deps, dict):
                    for name, value in deps.items():
                        if _normalize(name) == "ops":
                            return source, _classify_poetry(value), None
            poetry_groups = poetry.get("group")
            if isinstance(poetry_groups, dict):
                for group in poetry_groups.values():
                    if not isinstance(group, dict):
                        continue
                    deps = group.get("dependencies")
                    if isinstance(deps, dict):
                        for name, value in deps.items():
                            if _normalize(name) == "ops":
                                return source, _classify_poetry(value), None

    return None


def _find_ops_in_requirements(
    requirements: pathlib.Path,
) -> tuple[str, str, int | None] | None:
    """Look for an ``ops`` line in a ``requirements.txt``-style file."""
    try:
        text = requirements.read_text()
    except OSError:
        return None
    for lineno, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.split("#", 1)[0].strip()
        if not stripped or stripped.startswith("-"):
            continue
        kind = _classify_pep508(stripped)
        if kind is not None:
            return "requirements.txt", kind, lineno
    return None


#: charmcraft plugins that resolve dependencies from ``pyproject.toml``
#: plus a lock file. Any ``requirements.txt`` alongside one of these is a
#: generated artefact, not a hand-written declaration, so the pinning
#: rules must not read it.
_LOCKFILE_PLUGINS = frozenset({"poetry", "uv"})


def _uses_lockfile_plugin(metadata: models.Yaml) -> bool:
    """Report whether any ``parts`` entry uses a lock-file-based plugin."""
    return any(
        part.get("plugin").value in _LOCKFILE_PLUGINS for _, part in metadata.get("parts").items()
    )


@functools.cache
def _find_ops_requirements(charm_dir: pathlib.Path) -> tuple[str, str, int | None] | None:
    """Scan ``requirements.txt`` once per charm, for both JUJU rules."""
    requirements = charm_dir / "requirements.txt"
    if not requirements.is_file():
        return None
    return _find_ops_in_requirements(requirements)


def _find_ops_dep(context: models.CharmContext) -> tuple[str, str, int | None] | None:
    """Return ``(source, kind, line)`` for the first ``ops`` dep found, or ``None``.

    Both JUJU rules share this scan and stop at the first hit — a charm
    should only declare ``ops`` in one place. ``pyproject.toml`` wins
    over ``requirements.txt`` when both are present, and
    ``requirements.txt`` is skipped altogether for charms whose
    charmcraft plugin generates it from a lock file.
    """
    if context.pyproject is not None:
        found = _find_ops_in_pyproject(context.pyproject)
        if found is not None:
            return found

    if _uses_lockfile_plugin(context.metadata):
        return None

    return _find_ops_requirements(context.charm_dir)


class OpsDependencyUnpinned(Rule):
    """Flag an ``ops`` dependency with no version specifier."""

    category = "JUJU"
    number = 3
    name = "ops-dependency-unpinned"
    description = "ops dependency has no version specifier"
    default_severity = models.Severity.WARNING

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        found = _find_ops_dep(context)
        if found is None or found[1] != "unpinned":
            return []
        source, _kind, line = found
        return [
            self.diagnostic(
                "ops dependency has no version specifier — "
                "charms should pin a supported range so dependency "
                "resolvers do not silently pull a major bump",
                path=source,
                line=line,
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
        found = _find_ops_dep(context)
        if found is None or found[1] != "exact":
            return []
        source, _kind, line = found
        return [
            self.diagnostic(
                "ops dependency is exactly pinned (`==`) — "
                "prefer a version range so security fixes flow in "
                "without a manual bump",
                path=source,
                line=line,
                fix_hint="Replace the `==` pin with a range, e.g. `ops>=2.17,<4`",
            )
        ]
