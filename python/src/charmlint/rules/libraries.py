"""Library rules — fetch-libs imports with PyPI equivalents.

As of Apr 2026, most charm libraries still live in their host charm repos
and require ``charmcraft fetch-libs``.  A growing subset has been lifted
into the ``canonical/charmlibs`` monorepo and published to PyPI under the
``charmlibs-*`` namespace; the import path also changes (``charms.foo.vN.bar``
→ ``charmlibs.bar``).  See ``design/UPSTREAM_AUDIT.md`` for the audit log
and cutoff.
"""

import re

from .. import models
from . import Rule

# Each entry: (PyPI package name, new import path shown to the user).
# Keys are the ``charms.<key>`` prefix captured by _IMPORT_RE.  For
# ``operator_libs_linux`` the replacement depends on the submodule, so we
# look that up in ``_OP_LIBS_LINUX_SUBMODULES`` and ignore this top-level
# entry.
_FETCH_LIBS_PYPI_MAP: dict[str, tuple[str, str]] = {
    "certificate_transfer_interface": (
        "charmlibs-interfaces-certificate-transfer",
        "from charmlibs.interfaces import certificate_transfer",
    ),
    "tls_certificates_interface": (
        "charmlibs-interfaces-tls-certificates",
        "from charmlibs.interfaces import tls_certificates",
    ),
}

# ``charms.operator_libs_linux.vN.<submodule>`` has a per-submodule PyPI
# replacement — each submodule lives in its own ``charmlibs-*`` package.
_OP_LIBS_LINUX_SUBMODULES: dict[str, tuple[str, str]] = {
    "apt": ("charmlibs-apt", "from charmlibs import apt"),
    "snap": ("charmlibs-snap", "from charmlibs import snap"),
    "passwd": ("charmlibs-passwd", "from charmlibs import passwd"),
    "sysctl": ("charmlibs-sysctl", "from charmlibs import sysctl"),
    "systemd": ("charmlibs-systemd", "from charmlibs import systemd"),
}

# Matches ``from charms.<prefix>.vN.<submodule>`` — captures both parts.
_IMPORT_RE = re.compile(r"from\s+charms\.(\w+)\.v\d+\.(\w+)")


def _resolve(prefix: str, submodule: str) -> tuple[str, str] | None:
    """Return ``(pypi_name, import_hint)`` for an import, or ``None``."""
    if prefix == "operator_libs_linux":
        return _OP_LIBS_LINUX_SUBMODULES.get(submodule)
    return _FETCH_LIBS_PYPI_MAP.get(prefix)


class FetchLibsHasPyPI(Rule):
    """Detect fetch-libs imports that have known PyPI equivalents."""

    id = "LIB001"
    name = "fetch-libs-has-pypi"
    description = "Charm library import has a PyPI equivalent"
    default_severity = models.Severity.WARNING

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        seen: set[tuple[str, str]] = set()

        for path, content in context.python_sources.items():
            for match in _IMPORT_RE.finditer(content):
                prefix = match.group(1)
                submodule = match.group(2)
                key = (prefix, submodule)
                if key in seen:
                    continue
                seen.add(key)

                resolved = _resolve(prefix, submodule)
                if resolved:
                    pypi_name, import_hint = resolved
                    line = content[: match.start()].count("\n") + 1
                    diagnostics.append(
                        self.diagnostic(
                            (
                                f"charms.{prefix}.v*.{submodule} — replace with PyPI package "
                                f"'{pypi_name}' ({import_hint})"
                            ),
                            path=str(path),
                            line=line,
                            fix_hint=f"pip install {pypi_name}",
                        )
                    )
        return diagnostics


class FetchLibsUnknownPyPI(Rule):
    """Detect fetch-libs imports with no known PyPI equivalent."""

    id = "LIB002"
    name = "fetch-libs-unknown-pypi"
    description = "Charm library import — no PyPI equivalent yet; keep fetch-libs"
    default_severity = models.Severity.INFO

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        seen: set[tuple[str, str]] = set()

        for path, content in context.python_sources.items():
            for match in _IMPORT_RE.finditer(content):
                prefix = match.group(1)
                submodule = match.group(2)
                key = (prefix, submodule)
                if key in seen:
                    continue
                seen.add(key)

                if _resolve(prefix, submodule) is None:
                    line_no = content[: match.start()].count("\n") + 1
                    diagnostics.append(
                        self.diagnostic(
                            (
                                f"charms.{prefix}.v*.{submodule} — no PyPI equivalent yet; "
                                "continue using `charmcraft fetch-libs`"
                            ),
                            path=str(path),
                            line=line_no,
                        )
                    )
        return diagnostics
