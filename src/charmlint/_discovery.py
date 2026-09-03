"""Finding the charm directories under a path charmlint was pointed at.

charmlint lints one charm at a time: a :class:`_models.CharmContext` holds
one charm's metadata, and its Python modules are scoped relative to that
charm's root. Repositories, though, do not always hold exactly one charm —
``openstack/sunbeam-charms`` has 84 of them under ``charms/``, and several
Canonical repositories ship a ``kubernetes/`` and a ``machine/`` variant
side by side.

This module turns the path the user gave into the list of charm roots below
it, so the linter can build one context per charm rather than reading one
charm's metadata and another charm's code.

The walk is deliberately conservative. A directory holding
``charmcraft.yaml`` or ``metadata.yaml`` *is* a charm, and the walk does not
descend into it: that stops a charm's own integration-test fixture charms
from being linted as though the user had asked for them, and it collapses
the reactive layout — where a built ``src/metadata.yaml`` sits under a
source ``metadata.yaml`` — back to the single charm it is. Everything else
here exists to keep the walk off trees that contain charm-shaped files but
no charm of the user's: virtualenvs, build output, and test data.
"""

import pathlib

# Directory names never descended into. Dotted directories (``.git``,
# ``.tox``, ``.venv``) are skipped separately, as is anything ending in
# ``.egg-info``.
_SKIP_DIRS = frozenset(
    {
        "build",
        "dist",
        "docs",
        "node_modules",
        "test",
        "tests",
        "venv",
        "__pycache__",
    }
)

# How far below the given path to look. ``charms/storage/cinder-volume-ceph``
# in sunbeam-charms is a real charm three levels down, and nothing in the
# Hyrum cache is a real charm deeper than that.
_MAX_DEPTH = 3

_METADATA_FILES = ("charmcraft.yaml", "metadata.yaml")


def is_charm_dir(directory: pathlib.Path) -> bool:
    """Return whether *directory* holds a charm's metadata."""
    return any((directory / name).is_file() for name in _METADATA_FILES)


def discover_charms(root: pathlib.Path) -> list[pathlib.Path]:
    """Return the charm directories at or below *root*, outermost first.

    ``[root]`` when *root* is itself a charm — the overwhelmingly common
    case, and the one that leaves single-charm behaviour untouched. An empty
    list when there is no charm to be found, which the caller reports rather
    than treating as a clean run.
    """
    found: list[pathlib.Path] = []

    def walk(directory: pathlib.Path, depth: int) -> None:
        if is_charm_dir(directory):
            found.append(directory)
            return
        if depth >= _MAX_DEPTH:
            return
        try:
            children = sorted(directory.iterdir())
        except OSError:
            return
        for child in children:
            if child.is_symlink() or not child.is_dir():
                continue
            if child.name.startswith(".") or child.name in _SKIP_DIRS:
                continue
            if child.name.endswith(".egg-info"):
                continue
            walk(child, depth + 1)

    walk(root, 0)
    return found
