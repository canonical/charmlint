"""Library rules — fetch-libs imports with PyPI equivalents.

Module shell + shared lookup tables for LIB001 and LIB002. The rule
classes follow in their own PRs.
"""

import re

from .. import _models as models
from . import Rule

# Each entry: (PyPI package name, new import path shown to the user).
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
