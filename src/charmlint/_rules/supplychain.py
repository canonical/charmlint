"""SUPPLYCHAIN rules — dependency and release hygiene.

A charm deploys more than its own source: everything it pulls in from
elsewhere, at build time or at deploy time. These rules check that the
charm records where each of those artefacts comes from and which
versions it accepts.
"""

import dataclasses
import functools
import pathlib
import re
from typing import Any

from .. import _models as models
from .. import _yaml
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
    #: 1-based line, or ``None`` when it can't be found. ``tomllib``
    #: discards positions, so for ``pyproject.toml`` the line is found
    #: by looking for the entry in the text (see :func:`_toml_line`),
    #: and a layout that lookup doesn't follow anchors to the file.
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


def _parse_poetry(
    value: Any, source: str, section: str, line: int | None = None
) -> _OpsDependency:
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
        line=line,
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


_TOML_HEADER_RE = re.compile(r"^\[\[?(?P<name>[^\[\]]+)\]\]?\s*(?:#.*)?$")


def _toml_line(text: str, table: str, key: str, entry: str | None = None) -> int | None:
    """Return the 1-based line declaring *entry* under *key* in ``[table]``.

    ``tomllib`` keeps no positions, but a dependency is almost always
    written the plain way: a ``[table]`` header, a ``key =`` line, and
    the requirement as a quoted string in the array that follows. That
    is enough to find the line without a positions-preserving parser.
    With no *entry*, the ``key =`` line itself is the answer (Poetry's
    ``ops = "^2"``). Anything written another way, such as a dotted key
    or an inline table, returns ``None`` and the finding anchors to the
    file instead.
    """
    quoted = (f'"{entry}"', f"'{entry}'") if entry is not None else ()
    key_re = re.compile(rf"""^\s*["']?{re.escape(key)}["']?\s*=""")
    in_table = after_key = False
    for lineno, line in enumerate(text.splitlines(), start=1):
        header = _TOML_HEADER_RE.match(line.strip())
        if header is not None:
            name = header.group("name").replace(" ", "").replace('"', "").replace("'", "")
            in_table = name == table
            after_key = False
            continue
        if not in_table:
            continue
        if not after_key and key_re.match(line):
            if entry is None:
                return lineno
            after_key = True
        if after_key and any(q in line for q in quoted):
            return lineno
    return None


def _find_ops_in_pyproject(data: dict[str, Any], text: str = "") -> _OpsDependency | None:
    """Look for an ``ops`` dependency across the common pyproject.toml layouts.

    *data* is the charm's parsed ``pyproject.toml``, read once by the
    linter core, and *text* the same file unparsed, which is only used
    to find the line (:func:`_toml_line`). ``None`` means no ``ops``
    dependency appears in any known location.
    """
    source = "pyproject.toml"

    # PEP 621 — [project.dependencies] and [project.optional-dependencies.*]
    project = data.get("project")
    if isinstance(project, dict):
        for entry in _walk_pep508_list(project.get("dependencies")):
            line = _toml_line(text, "project", "dependencies", entry)
            dep = _parse_pep508(entry, source, "project.dependencies", line)
            if dep is not None and not dep.is_test_only:
                return dep
        optional = project.get("optional-dependencies")
        if isinstance(optional, dict):
            for name, entries in optional.items():
                for entry in _walk_pep508_list(entries):
                    line = _toml_line(text, "project.optional-dependencies", name, entry)
                    section = f"project.optional-dependencies.{name}"
                    dep = _parse_pep508(entry, source, section, line)
                    if dep is not None and not dep.is_test_only:
                        return dep

    # PEP 735 — [dependency-groups.*]
    groups = data.get("dependency-groups")
    if isinstance(groups, dict):
        for name, entries in groups.items():
            for entry in _walk_pep508_list(entries):
                line = _toml_line(text, "dependency-groups", name, entry)
                dep = _parse_pep508(entry, source, f"dependency-groups.{name}", line)
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
                            line = _toml_line(text, f"tool.poetry.{key}", name)
                            dep = _parse_poetry(value, source, f"tool.poetry.{key}", line)
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
                                table = f"tool.poetry.group.{group_name}.dependencies"
                                line = _toml_line(text, table, name)
                                dep = _parse_poetry(value, source, table, line)
                                if not dep.is_test_only:
                                    return dep

    return None


def _find_ops_in_requirements(
    requirements: pathlib.Path, name: str = "requirements.txt"
) -> _OpsDependency | None:
    """Look for an ``ops`` line in a ``requirements.txt``-style file.

    *name* is what the diagnostic calls the file. It defaults to
    ``requirements.txt`` because that is the file almost every charm
    uses, but the ``python`` plugin lets a charm name its requirements
    files itself, and a finding should point at the file the charm
    actually declared rather than at one it does not have.
    """
    try:
        text = requirements.read_text()
    except OSError:
        return None
    for lineno, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.split("#", 1)[0].strip()
        if not stripped or stripped.startswith("-"):
            continue
        dep = _parse_pep508(stripped, name, name, lineno)
        if dep is not None and not dep.is_test_only:
            return dep
    return None


#: charmcraft plugins that resolve dependencies from ``pyproject.toml``
#: plus a lock file. Any ``requirements.txt`` alongside one of these is a
#: generated artefact, not a hand-written declaration, so the pinning
#: rules must not read it.
#:
#: This is a narrow guard, and deliberately so. Across the corpus it
#: changes the outcome for two charms — the ``kubernetes`` and ``machine``
#: charms of ``opensearch-dashboards-operator``, which export a
#: ``requirements.txt`` from ``poetry.lock`` (``--only main``) purely so
#: the pins are visible inside the built ``.charm``. That export pins
#: ``ops`` exactly, which is what a lock file is for; without this guard
#: SUPPLYCHAIN-006 would flag it.
_LOCKFILE_PLUGINS = frozenset({"poetry", "uv"})

#: Every charmcraft plugin that builds the charm's Python environment,
#: and so decides where the charm's dependencies are declared. The rest
#: of the plugins a charm uses — ``nil``, ``dump``, ``reactive`` — put
#: files in the payload without resolving anything, and say nothing
#: about where ``ops`` is declared.
_DEPENDENCY_PLUGINS = _LOCKFILE_PLUGINS | frozenset({"charm", "python"})


def _dependency_part(metadata: models.Yaml) -> models.Yaml | None:
    """Return the ``parts`` entry that builds the charm's Python environment.

    A charm has at most one. Across the corpus, 329 of 655 charms
    declare exactly one part using a dependency-resolving plugin and
    **none declares two**; the sets are disjoint as well as unique
    (``uv`` 198, ``poetry`` 79, ``charm`` 52). The remaining 326 either
    declare ``parts`` using only ``nil``, ``dump`` or ``reactive``, or
    declare no ``parts`` at all — so "no dependency-resolving part" is
    the common case, not an error, and the caller falls back to the
    default ``requirements.txt`` for it.
    """
    for _, part in metadata.get("parts").items():
        if part.get("plugin").value in _DEPENDENCY_PLUGINS:
            return part
    return None


def _requirements_files(context: models.CharmContext) -> tuple[tuple[pathlib.Path, str], ...]:
    """Return the requirements files the charm's build plugin actually reads.

    Each entry is the path to read and the name to call it in a
    diagnostic. An empty tuple means the plugin resolves dependencies
    from ``pyproject.toml`` and a lock file, so there is no hand-written
    requirements file to read at all.
    """
    part = _dependency_part(context.metadata)
    default = ((context.charm_dir / "requirements.txt", "requirements.txt"),)
    if part is None:
        return default
    plugin = part.get("plugin").value
    if plugin in _LOCKFILE_PLUGINS:
        return ()
    if plugin == "python":
        # The python plugin names its own requirements files, and a
        # charm using it need not call them requirements.txt.
        declared = tuple(
            (context.charm_dir / str(entry.value), str(entry.value))
            for entry in part.get("python-requirements").elements or ()
            if entry.value
        )
        if declared:
            return declared
    return default


@functools.cache
def _find_ops_requirements(
    files: tuple[tuple[pathlib.Path, str], ...],
) -> _OpsDependency | None:
    """Scan the charm's requirements files once, for both pinning rules."""
    for path, name in files:
        if not path.is_file():
            continue
        dep = _find_ops_in_requirements(path, name)
        if dep is not None:
            return dep
    return None


def _find_ops_dep(context: models.CharmContext) -> _OpsDependency | None:
    """Return the charm's runtime ``ops`` dependency, or ``None``.

    Both pinning rules share this scan and stop at the first hit that
    is not the test harness. Declaring ``ops`` more than once is the
    norm rather than the exception — 245 of the 417 corpus charms that
    declare it at all do so twice or more, almost always runtime
    ``ops`` alongside ``ops[testing]`` in a test group — so
    :attr:`_OpsDependency.is_test_only` declarations are stepped over
    rather than returned. ``pyproject.toml`` wins over the requirements
    files when both are present, and which requirements files those are
    is decided by the charm's build plugin — see
    :func:`_requirements_files`.
    """
    if context.pyproject is not None:
        try:
            text = (context.charm_dir / "pyproject.toml").read_text()
        except OSError:
            text = ""
        dep = _find_ops_in_pyproject(context.pyproject, text)
        if dep is not None:
            return dep

    return _find_ops_requirements(_requirements_files(context))


class OciImageMissingUpstreamSource(Rule):
    """Flag an ``oci-image`` resource with no ``upstream-source``."""

    category = "SUPPLYCHAIN"
    number = 1
    name = "oci-image-missing-upstream-source"
    description = "oci-image resource declared without an 'upstream-source'"
    default_severity = models.Severity.INFO

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        candidates = [
            (name, resource)
            for name, resource in context.metadata.get("resources").items()
            if resource.get("type").value == "oci-image" and not resource.get("upstream-source")
        ]
        if not candidates:
            return []

        # `upstream-source` names the image the resource is built from, so
        # it has nothing to say about an image this repository builds
        # itself: for those the build recipe is the record of provenance.
        local = _locally_built_images(context.charm_dir)
        diagnostics: list[models.Diagnostic] = []
        for name, resource in candidates:
            stem = _normalise_image_name(name)
            for suffix in _IMAGE_SUFFIXES:
                stem = stem.removesuffix(suffix)
            if stem in local or _normalise_image_name(name) in local:
                continue
            diagnostics.append(
                self.diagnostic(
                    f"OCI image resource '{name}' has no 'upstream-source', so there is "
                    "no record of which image it is built from",
                    # A split-metadata charm can declare `resources` in
                    # metadata.yaml, where the diagnostic — and any noqa
                    # silencing it — then belongs.
                    path=resource.source,
                    line=resource.line,
                    fix_hint=(
                        f"Add 'upstream-source' under resources.{name}, naming the image "
                        "the resource is built from (e.g. 'ghcr.io/canonical/foo:1.2.3')"
                    ),
                )
            )
        return diagnostics


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


_IMAGE_SUFFIXES = ("-image", "_image")


def _normalise_image_name(name: object) -> str:
    """Fold a rock, directory, or resource name to one comparable form."""
    return str(name).replace("_", "-").lower()


def _locally_built_images(charm_dir: pathlib.Path) -> set[str]:
    """Return the names of images this repository builds for itself.

    A rock or Dockerfile in the charm directory, or up to two levels
    below it, names an image the charm's own CI builds and uploads. So
    does one up to two levels below the repository root, since in a
    monorepo the rock is often a sibling of the charm (``app/charm/``
    beside ``app/rockcraft.yaml``) or sits at the top of the repository.
    The candidate names are the rock's declared ``name`` and the
    directory holding the build recipe, since the ``foo_rock/``,
    ``rock/`` and ``foo_rocks/<component>/`` layouts are all common.
    """
    charm_dir = charm_dir.resolve()
    names: set[str] = set()
    for root in {charm_dir, _repo_root(charm_dir)}:
        for depth in ("", "*/", "*/*/"):
            for rockcraft in root.glob(f"{depth}rockcraft.yaml"):
                try:
                    declared = _yaml.load(rockcraft).get("name")
                except _yaml.FileLoadError:
                    declared = models.Yaml.absent(rockcraft.name)
                if isinstance(declared.value, str):
                    names.add(_normalise_image_name(declared.value))
                names.add(
                    _normalise_image_name(
                        rockcraft.parent.name.removesuffix("_rock").removesuffix("-rock")
                    )
                )
            for dockerfile in root.glob(f"{depth}Dockerfile"):
                names.add(_normalise_image_name(dockerfile.parent.name))
    return names


def _repo_root(charm_dir: pathlib.Path) -> pathlib.Path:
    """Return the root of the git repository holding the charm.

    Falls back to the charm directory itself when it is not in a git
    repository, so the search never wanders further than it would have.
    """
    for directory in (charm_dir, *charm_dir.parents):
        if (directory / ".git").exists():
            return directory
    return charm_dir
