"""SUPPLYCHAIN rules — dependency and release hygiene."""

import dataclasses
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
    (?:\[(?P<extras>[^\]]*)\])?            # optional [extras], e.g. ops[tracing]
    \s*
    (?P<rest>.*)                           # the version specifier and/or a PEP 508 marker
    """,
    re.VERBOSE | re.DOTALL,
)


@dataclasses.dataclass(frozen=True)
class _OpsDependency:
    """A charm's declared ``ops`` dependency, and where it was declared.

    Every rule about the ``ops`` dependency works from one of
    these, so the charm's packaging is parsed once and interrogated
    many times rather than each rule re-deriving the answer it happens
    to need. Keeping the specifier and the section rather than a
    collapsed verdict is what lets a later rule ask a question the
    current two do not — whether there is an upper bound, whether the
    pinned version is an LTS, whether the section it was found in is
    one a charm ought to be using.
    """

    #: The version specifier exactly as written, e.g. ``">=2.23,<4"``.
    #: Empty when the dependency is declared with no specifier at all.
    specifier: str
    #: Extras requested alongside it, e.g. ``("tracing",)``.
    extras: tuple[str, ...]
    #: The file it was declared in, relative to the charm directory.
    source: str
    #: Where within that file, as a dotted path for ``pyproject.toml``
    #: (``"project.dependencies"``) or the file name for a flat
    #: requirements file. Names a place a charm author can go and look.
    section: str
    #: 1-based line, or ``None`` for a ``pyproject.toml`` match —
    #: ``tomllib`` discards positions, so a finding there anchors to
    #: the file.
    line: int | None

    @property
    def is_unpinned(self) -> bool:
        """Whether it carries no version constraint at all."""
        return not self.specifier or self.specifier == "*"

    @property
    def is_exact(self) -> bool:
        """Whether it is pinned to a single version with ``==``."""
        return self.specifier.startswith("==")

    @property
    def is_test_only(self) -> bool:
        """Whether this declaration is the testing harness rather than the runtime.

        ``ops[testing]`` pulls in ``ops.testing``, which runs in the
        test environment and never ships in the charm. Neither pinning
        rule has anything useful to say about it: a test harness wants
        the version the tests were written against, not a range chosen
        so security fixes flow into production.
        """
        return "testing" in self.extras

    @property
    def where(self) -> str:
        """A phrase naming the section, for a diagnostic message.

        Empty for a flat requirements file, where the section *is* the
        file the diagnostic already points at, and naming it again
        would only pad the message. For ``pyproject.toml``, where
        there is no line to anchor to and a charm can declare ``ops``
        in any of half a dozen places, it is the only thing telling
        the author which one to go and edit.
        """
        if self.section == self.source:
            return ""
        return f" in `{self.section}`"


def _normalize(name: str) -> str:
    """PEP 503 name normalisation — dashes/underscores/dots collapse and lowercase."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _parse_pep508(
    entry: str, source: str, section: str, line: int | None = None
) -> _OpsDependency | None:
    """Parse a PEP 508 requirement string, returning ``None`` if it isn't ``ops``."""
    match = _PEP508_RE.match(entry)
    if match is None or _normalize(match.group("name")) != "ops":
        return None
    # Drop any environment marker: `ops>=2.23; python_version < "3.12"`
    # constrains when the dependency applies, not which versions satisfy it.
    specifier = match.group("rest").split(";", 1)[0].strip()
    return _OpsDependency(
        specifier=specifier,
        extras=_split_extras(match.group("extras")),
        source=source,
        section=section,
        line=line,
    )


def _parse_poetry(value: Any, source: str, section: str) -> _OpsDependency:
    """Parse a Poetry dependency value (bare string, or table with ``version``)."""
    if isinstance(value, dict):
        specifier = str(value.get("version", ""))
        extras = value.get("extras")
        extras = tuple(str(e) for e in extras) if isinstance(extras, list) else ()
    else:
        specifier = str(value)
        extras = ()
    return _OpsDependency(
        specifier=specifier.strip(),
        extras=extras,
        source=source,
        section=section,
        line=None,
    )


def _split_extras(extras: str | None) -> tuple[str, ...]:
    """Split the bracketed extras of a PEP 508 requirement into a tuple."""
    if not extras:
        return ()
    stripped = (part.strip() for part in extras.split(","))
    return tuple(part for part in stripped if part)


def _walk_pep508_list(entries: Any):
    """Yield PEP 508 strings from a value that should be a list of requirements."""
    if not isinstance(entries, list):
        return
    for entry in entries:
        if isinstance(entry, str):
            yield entry


def _find_ops_in_pyproject(data: dict[str, Any]) -> _OpsDependency | None:
    """Look for an ``ops`` dependency across the common pyproject.toml layouts.

    *data* is the charm's parsed ``pyproject.toml``, read once by the
    linter core. ``None`` means no ``ops`` dependency appears in any
    known location.
    """
    source = "pyproject.toml"

    # PEP 621 — [project.dependencies] and [project.optional-dependencies.*]
    project = data.get("project")
    if isinstance(project, dict):
        for entry in _walk_pep508_list(project.get("dependencies")):
            dep = _parse_pep508(entry, source, "project.dependencies")
            if dep is not None and not dep.is_test_only:
                return dep
        optional = project.get("optional-dependencies")
        if isinstance(optional, dict):
            for name, entries in optional.items():
                for entry in _walk_pep508_list(entries):
                    dep = _parse_pep508(entry, source, f"project.optional-dependencies.{name}")
                    if dep is not None and not dep.is_test_only:
                        return dep

    # PEP 735 — [dependency-groups.*]
    groups = data.get("dependency-groups")
    if isinstance(groups, dict):
        for name, entries in groups.items():
            for entry in _walk_pep508_list(entries):
                dep = _parse_pep508(entry, source, f"dependency-groups.{name}")
                if dep is not None and not dep.is_test_only:
                    return dep

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
                            dep = _parse_poetry(value, source, f"tool.poetry.{key}")
                            if not dep.is_test_only:
                                return dep
            poetry_groups = poetry.get("group")
            if isinstance(poetry_groups, dict):
                for group_name, group in poetry_groups.items():
                    if not isinstance(group, dict):
                        continue
                    deps = group.get("dependencies")
                    if isinstance(deps, dict):
                        for name, value in deps.items():
                            if _normalize(name) == "ops":
                                dep = _parse_poetry(
                                    value,
                                    source,
                                    f"tool.poetry.group.{group_name}.dependencies",
                                )
                                if not dep.is_test_only:
                                    return dep

    return None


def _find_ops_in_requirements(requirements: pathlib.Path) -> _OpsDependency | None:
    """Look for an ``ops`` line in a ``requirements.txt``-style file."""
    try:
        text = requirements.read_text()
    except OSError:
        return None
    for lineno, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.split("#", 1)[0].strip()
        if not stripped or stripped.startswith("-"):
            continue
        dep = _parse_pep508(stripped, "requirements.txt", "requirements.txt", lineno)
        if dep is not None and not dep.is_test_only:
            return dep
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
def _find_ops_requirements(charm_dir: pathlib.Path) -> _OpsDependency | None:
    """Scan ``requirements.txt`` once per charm, for both pinning rules."""
    requirements = charm_dir / "requirements.txt"
    if not requirements.is_file():
        return None
    return _find_ops_in_requirements(requirements)


def _find_ops_dep(context: models.CharmContext) -> _OpsDependency | None:
    """Return the charm's runtime ``ops`` dependency, or ``None``.

    Both pinning rules share this scan and stop at the first hit that
    is not the test harness. Declaring ``ops`` more than once is the
    norm rather than the exception — 245 of the 417 corpus charms that
    declare it at all do so twice or more, almost always runtime
    ``ops`` alongside ``ops[testing]`` in a test group — so
    :attr:`_OpsDependency.is_test_only` declarations are stepped over
    rather than returned. ``pyproject.toml`` wins over
    ``requirements.txt`` when both are present, and ``requirements.txt``
    is skipped altogether for charms whose charmcraft plugin generates
    it from a lock file.
    """
    if context.pyproject is not None:
        dep = _find_ops_in_pyproject(context.pyproject)
        if dep is not None:
            return dep

    if _uses_lockfile_plugin(context.metadata):
        return None

    return _find_ops_requirements(context.charm_dir)


class OpsDependencyUnpinned(Rule):
    """Flag an ``ops`` dependency with no version specifier."""

    category = "SUPPLYCHAIN"
    number = 5
    name = "ops-dependency-unpinned"
    description = "ops dependency has no version specifier"
    default_severity = models.Severity.WARNING

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        dep = _find_ops_dep(context)
        if dep is None or not dep.is_unpinned:
            return []
        return [
            self.diagnostic(
                f"ops dependency has no version specifier{dep.where} — "
                "charms should pin a supported range so dependency "
                "resolvers do not silently pull a major bump",
                path=dep.source,
                line=dep.line,
                fix_hint="Add a version range, e.g. `ops>=2.23,<4`",
            )
        ]


class OpsDependencyExactlyPinned(Rule):
    """Flag an ``ops`` dependency pinned with ``==``."""

    category = "SUPPLYCHAIN"
    number = 6
    name = "ops-dependency-exactly-pinned"
    description = "ops dependency pinned with `==`"
    default_severity = models.Severity.INFO

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        dep = _find_ops_dep(context)
        if dep is None or not dep.is_exact:
            return []
        return [
            self.diagnostic(
                f"ops dependency is exactly pinned (`==`){dep.where} — "
                "prefer a version range so security fixes flow in "
                "without a manual bump",
                path=dep.source,
                line=dep.line,
                fix_hint="Replace the `==` pin with a range, e.g. `ops>=2.23,<4`",
            )
        ]
