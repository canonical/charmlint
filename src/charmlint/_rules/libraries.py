"""Library rules — fetch-libs imports with PyPI equivalents."""

import re

from .. import _models as models
from ._base import Rule

# Two families of fetch-libs imports have known PyPI replacements:
#
# 1. ``charms.operator_libs_linux.vN.<submodule>`` — each submodule ships
#    as its own ``charmlibs-<submodule>`` package.
# 2. ``charms.<name>_interface.vN.<lib>`` — the shared interface libs
#    now live under ``charmlibs-interfaces-<name>``.
#
# The tables below are the source-of-truth for both cases. They are
# regenerated from the PyPI ``charmlibs-*`` namespace by
# ``tools/refresh_charmlibs_map.py``.

_OP_LIBS_LINUX_SUBMODULES: dict[str, tuple[str, str]] = {
    "apt": ("charmlibs-apt", "from charmlibs import apt"),
    "passwd": ("charmlibs-passwd", "from charmlibs import passwd"),
    "snap": ("charmlibs-snap", "from charmlibs import snap"),
    "sysctl": ("charmlibs-sysctl", "from charmlibs import sysctl"),
    "systemd": ("charmlibs-systemd", "from charmlibs import systemd"),
}

# Prefix (without the ``_interface`` suffix) → (pypi name, import hint).
# Kept as a table rather than derived from the prefix, because the
# fetch-libs charm name doesn't always follow ``<x>_interface``.
_INTERFACE_PREFIXES: dict[str, tuple[str, str]] = {
    "certificate_transfer_interface": (
        "charmlibs-interfaces-certificate-transfer",
        "from charmlibs.interfaces import certificate_transfer",
    ),
    "tls_certificates_interface": (
        "charmlibs-interfaces-tls-certificates",
        "from charmlibs.interfaces import tls_certificates",
    ),
}

_IMPORT_RE = re.compile(r"from\s+charms\.(\w+)\.v\d+\.(\w+)")


def _resolve(prefix: str, submodule: str) -> tuple[str, str] | None:
    """Return ``(pypi_name, import_hint)`` for an import, or ``None``."""
    if prefix == "operator_libs_linux":
        return _OP_LIBS_LINUX_SUBMODULES.get(submodule)
    return _INTERFACE_PREFIXES.get(prefix)


class FetchLibsHasPyPI(Rule):
    """Detect fetch-libs imports that have known PyPI equivalents."""

    category = "LIBRARY"
    number = 1
    name = "fetch-libs-has-pypi"
    description = "Charm library import has a PyPI equivalent"
    default_severity = models.Severity.WARNING
    reference_url = "https://canonical.com/juju/docs/charmlibs/"

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        seen: set[tuple[str, str]] = set()

        for path, content in context.python_sources.items():
            for match in _IMPORT_RE.finditer(content):
                prefix, submodule = match.group(1), match.group(2)
                key = (prefix, submodule)
                if key in seen:
                    continue
                seen.add(key)

                resolved = _resolve(prefix, submodule)
                if resolved is None:
                    continue
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
