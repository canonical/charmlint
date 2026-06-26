"""Library rules — fetch-libs imports with PyPI equivalents.

Module shell + shared lookup tables for LIB001 and LIB002. The rule
classes follow in their own PRs.
"""

import re

from .. import _models as models  # noqa: F401  # used by the rule PRs that follow
from . import Rule  # noqa: F401  # used by the rule PRs that follow

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
