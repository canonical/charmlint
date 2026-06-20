"""Charm-library metadata and semver rules.

The ``charm-library`` skill describes a strict on-disk shape for any
``lib/charms/<charm>/v<N>/<name>.py`` file: the four module-level
constants (``LIBID``, ``LIBAPI``, ``LIBPATCH``, ``PYDEPS``), the
relationship between ``LIBAPI`` and the ``v<N>`` directory, and the
"keep the old file when you bump major" rule that means a single
library can have ``v0/foo.py`` and ``v1/foo.py`` side-by-side.

The existing ``libraries.py`` module covers the *fetch-libs* PyPI
migration angle (``LIB001``, ``LIB002``); this module covers the
metadata + breaking-change angle the skill body used to recite to
the agent every turn.

Out of scope: ``LIBPATCH`` decreases between git revisions.  The
charmlint context is the working tree only and we do not shell out
to git from rule modules.
"""

import ast
import pathlib
import re

from .. import models
from . import Rule

# `lib/charms/<charm>/v<N>/<name>.py`
_LIB_PATH_RE = re.compile(r"lib/charms/([^/]+)/v(\d+)/([^/]+)\.py$")

# A LIBID looks like a UUID4 hex string, but charmcraft historically
# accepts any hex blob.  Tighten just enough to catch obvious typos
# (empty string, too short, non-hex).
_LIBID_RE = re.compile(r"^[0-9a-fA-F]{16,}$")


def _iter_library_files(
    python_files: list[pathlib.Path],
    charm_dir: pathlib.Path,
) -> list[tuple[pathlib.Path, str, int, str]]:
    """Yield ``(path, charm_name, api_version, library_name)`` per library file."""
    out: list[tuple[pathlib.Path, str, int, str]] = []
    for path in python_files:
        try:
            rel = path.relative_to(charm_dir).as_posix()
        except ValueError:
            rel = path.as_posix()
        match = _LIB_PATH_RE.search(rel)
        if not match:
            continue
        charm = match.group(1)
        api = int(match.group(2))
        name = match.group(3)
        out.append((path, charm, api, name))
    return out


def _module_constants(tree: ast.AST) -> dict[str, ast.expr]:
    """Map module-level constant name → its assigned-value AST node."""
    consts: dict[str, ast.expr] = {}
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    consts[target.id] = node.value
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.value is not None
        ):
            consts[node.target.id] = node.value
    return consts


def _string_value(node: ast.expr) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _int_value(node: ast.expr) -> int | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, int) else None


class LibraryMetadataShape(Rule):
    """Verify every charm-library file declares LIBID/LIBAPI/LIBPATCH correctly."""

    id = "LIB003"
    name = "library-metadata-shape"
    description = "Charm-library file is missing or has malformed LIBID/LIBAPI/LIBPATCH"
    default_severity = models.Severity.ERROR

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        for path, _charm, dir_api, _name in _iter_library_files(
            context.python_files, context.charm_dir
        ):
            content = context.python_sources.get(path, "")
            if not content:
                continue
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue
            consts = _module_constants(tree)
            diagnostics.extend(self._check_file(path, dir_api, consts))
        return diagnostics

    def _check_file(
        self,
        path: pathlib.Path,
        dir_api: int,
        consts: dict[str, ast.expr],
    ) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        path_str = str(path)

        # LIBID: must be present, a string, and look like a hex blob.
        libid_node = consts.get("LIBID")
        if libid_node is None:
            diagnostics.append(
                self.diagnostic(
                    "Library is missing LIBID — `charmcraft register-lib` "
                    "assigns one on first publish",
                    path=path_str,
                )
            )
        else:
            value = _string_value(libid_node)
            if value is None:
                diagnostics.append(
                    self.diagnostic(
                        "LIBID must be a string literal", path=path_str, line=libid_node.lineno
                    )
                )
            elif not _LIBID_RE.match(value):
                diagnostics.append(
                    self.diagnostic(
                        f"LIBID does not look like a hex identifier (got {value!r})",
                        path=path_str,
                        line=libid_node.lineno,
                    )
                )

        # LIBAPI: must be int and match the v<N> directory.
        libapi_node = consts.get("LIBAPI")
        if libapi_node is None:
            diagnostics.append(self.diagnostic("Library is missing LIBAPI", path=path_str))
        else:
            value = _int_value(libapi_node)
            if value is None:
                diagnostics.append(
                    self.diagnostic(
                        "LIBAPI must be an integer literal",
                        path=path_str,
                        line=libapi_node.lineno,
                    )
                )
            elif value != dir_api:
                diagnostics.append(
                    self.diagnostic(
                        f"LIBAPI={value} does not match directory v{dir_api} — "
                        f"breaking-change libraries live in a new v<N+1>/ folder",
                        path=path_str,
                        line=libapi_node.lineno,
                        fix_hint=f"Set LIBAPI = {dir_api} or move the file to v{value}/",
                    )
                )

        # LIBPATCH: must be a positive int.
        libpatch_node = consts.get("LIBPATCH")
        if libpatch_node is None:
            diagnostics.append(
                self.diagnostic(
                    "Library is missing LIBPATCH — bump on every change",
                    path=path_str,
                )
            )
        else:
            value = _int_value(libpatch_node)
            if value is None:
                diagnostics.append(
                    self.diagnostic(
                        "LIBPATCH must be an integer literal",
                        path=path_str,
                        line=libpatch_node.lineno,
                    )
                )
            elif value < 0:
                diagnostics.append(
                    self.diagnostic(
                        f"LIBPATCH={value} must be non-negative",
                        path=path_str,
                        line=libpatch_node.lineno,
                    )
                )

        return diagnostics


def _public_top_level_names(tree: ast.AST) -> set[str]:
    """Collect public top-level FunctionDef/ClassDef/Assign names in a module."""
    names: set[str] = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not node.name.startswith("_"):
                names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and not target.id.startswith("_"):
                    names.add(target.id)
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and not node.target.id.startswith("_")
        ):
            names.add(node.target.id)
    return names


class LibraryBreakingChange(Rule):
    """Flag public names removed between sibling-versioned library files."""

    id = "LIB004"
    name = "library-breaking-change"
    description = "Public name removed between v<N> and v<N+1> of the same library"
    default_severity = models.Severity.WARNING

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        # Group library files by ``(charm, name)`` so versions of the same
        # library can be compared.
        by_lib: dict[tuple[str, str], list[tuple[int, pathlib.Path]]] = {}
        for path, charm, api, name in _iter_library_files(context.python_files, context.charm_dir):
            by_lib.setdefault((charm, name), []).append((api, path))

        diagnostics: list[models.Diagnostic] = []
        for (_charm, lib_name), versions in by_lib.items():
            if len(versions) < 2:
                continue
            versions.sort()
            for (older_api, older_path), (newer_api, newer_path) in zip(
                versions, versions[1:], strict=False
            ):
                older_names = self._public_names(context, older_path)
                newer_names = self._public_names(context, newer_path)
                if older_names is None or newer_names is None:
                    continue
                removed = older_names - newer_names
                if not removed:
                    continue
                diagnostics.append(
                    self.diagnostic(
                        (
                            f"Library '{lib_name}' v{newer_api} drops public name(s) "
                            f"{sorted(removed)} present in v{older_api} — keep the old "
                            f"file on disk so existing consumers continue to fetch v{older_api}"
                        ),
                        path=str(newer_path),
                        fix_hint=(
                            "Verify the older v<N>/ file still exists; do not "
                            "rename or remove public names within a major version"
                        ),
                    )
                )
        return diagnostics

    @staticmethod
    def _public_names(context: models.CharmContext, path: pathlib.Path) -> set[str] | None:
        content = context.python_sources.get(path, "")
        if not content:
            return None
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return None
        return _public_top_level_names(tree)
