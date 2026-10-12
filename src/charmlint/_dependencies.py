"""Python dependency declarations in a charm's packaging files.

The rules that ask what a charm depends on (the ``ops`` pinning rules,
the ``ops-scenario`` rule) share this, so the layouts a
``pyproject.toml`` can declare a dependency in, and how a requirement
names its distribution, are written down once. Each rule decides for
itself which declarations it cares about.
"""

import dataclasses
import re
from collections.abc import Iterator
from typing import Any

_NAME = re.compile(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def normalise(name: str) -> str:
    """PEP 503 name normalisation: runs of ``-_.`` collapse, and case folds."""
    return re.sub(r"[-_.]+", "-", name).lower()


def requirement_name(requirement: str) -> str | None:
    """Return the normalised distribution name a PEP 508 requirement names.

    ``None`` when *requirement* doesn't start with a name, such as a
    ``-r other.txt`` option line.
    """
    match = _NAME.match(requirement)
    return normalise(match.group(1)) if match else None


@dataclasses.dataclass(frozen=True)
class Declaration:
    """One dependency declared in a ``pyproject.toml``."""

    #: The dotted path of the list or table it was declared in, such as
    #: ``"project.dependencies"`` or ``"tool.poetry.group.unit.dependencies"``.
    section: str
    #: The PEP 503 normalised distribution name.
    name: str
    #: The PEP 508 requirement string, for an entry in a PEP 621 or
    #: PEP 735 list. ``None`` for a Poetry entry.
    requirement: str | None
    #: Poetry's value for the entry (a version string, or a table with
    #: ``version`` and ``extras``). ``None`` for a PEP 508 entry.
    poetry_value: Any = None


def pyproject_declarations(data: dict[str, Any]) -> Iterator[Declaration]:
    """Yield every dependency declared in a parsed ``pyproject.toml``.

    The layouts are visited in a fixed order: PEP 621
    ``project.dependencies`` then ``project.optional-dependencies``,
    PEP 735 ``dependency-groups``, then Poetry's ``dependencies``,
    legacy ``dev-dependencies`` and ``group.<name>.dependencies``.
    Values of the wrong type are skipped: ``pyproject.toml`` belongs
    to the build tool, which reports a misshapen one itself.
    """
    project = data.get("project")
    if isinstance(project, dict):
        yield from _pep508_list(project.get("dependencies"), "project.dependencies")
        optional = project.get("optional-dependencies")
        if isinstance(optional, dict):
            for name, entries in optional.items():
                yield from _pep508_list(entries, f"project.optional-dependencies.{name}")
    groups = data.get("dependency-groups")
    if isinstance(groups, dict):
        for name, entries in groups.items():
            yield from _pep508_list(entries, f"dependency-groups.{name}")
    tool = data.get("tool")
    poetry = tool.get("poetry") if isinstance(tool, dict) else None
    if not isinstance(poetry, dict):
        return
    for key in ("dependencies", "dev-dependencies"):
        yield from _poetry_table(poetry.get(key), f"tool.poetry.{key}")
    poetry_groups = poetry.get("group")
    if isinstance(poetry_groups, dict):
        for name, group in poetry_groups.items():
            if isinstance(group, dict):
                yield from _poetry_table(
                    group.get("dependencies"), f"tool.poetry.group.{name}.dependencies"
                )


def _pep508_list(entries: Any, section: str) -> Iterator[Declaration]:
    """Yield a declaration for each PEP 508 string in a requirements list."""
    if not isinstance(entries, list):
        return
    for entry in entries:
        if not isinstance(entry, str):
            continue
        name = requirement_name(entry)
        if name is not None:
            yield Declaration(section=section, name=name, requirement=entry)


def _poetry_table(table: Any, section: str) -> Iterator[Declaration]:
    """Yield a declaration for each entry in a Poetry dependency table."""
    if not isinstance(table, dict):
        return
    for name, value in table.items():
        yield Declaration(
            section=section, name=normalise(name), requirement=None, poetry_value=value
        )


def requirement_lines(text: str) -> Iterator[tuple[int, str]]:
    """Yield ``(line, requirement)`` for each requirement in a requirements file.

    Comments, blank lines and option lines (``-r``, ``--hash``, ``-e``)
    are skipped.
    """
    for lineno, raw in enumerate(text.splitlines(), start=1):
        requirement = raw.split("#", 1)[0].strip()
        if requirement and not requirement.startswith("-"):
            yield lineno, requirement
