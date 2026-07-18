"""Library rules — fetch-libs imports with PyPI equivalents."""

import re

from .. import _models as models
from ._base import Rule

# Two families of fetch-libs imports have known PyPI replacements:
#
# 1. ``charms.operator_libs_linux.vN.<submodule>`` — each submodule ships
#    as its own ``charmlibs-<submodule>`` package.
# 2. ``charms.<owner>.vN.<lib>`` — a shared interface library. The
#    ``<owner>`` charm varies by lib (tls-certificates-interface,
#    hydra-operator, traefik-k8s, …), so we match on the ``<lib>``
#    module name — that's the interface-contract identity, and it's
#    stable across owners.
#
# Both tables are refreshed against
# https://canonical.com/juju/docs/charmlibs/reference/charmlibs-interfaces/
# and pypi.org/simple/. ``tools/refresh_charmlibs_map.py`` lists the
# live namespace.

_OP_LIBS_LINUX_SUBMODULES: frozenset[str] = frozenset(
    {"apt", "passwd", "snap", "sysctl", "systemd"}
)

# ``<lib module>`` → PyPI name for charmlibs-interfaces-*.
_INTERFACE_LIBS: dict[str, str] = {
    "certificate_transfer": "charmlibs-interfaces-certificate-transfer",
    "forward_auth": "charmlibs-interfaces-forward-auth",
    "gateway_metadata": "charmlibs-interfaces-gateway-metadata",
    "istio_ingress_route": "charmlibs-interfaces-istio-ingress-route",
    "istio_metadata": "charmlibs-interfaces-istio-metadata",
    "istio_request_auth": "charmlibs-interfaces-istio-request-auth",
    "k8s_backup_target": "charmlibs-interfaces-k8s-backup-target",
    "oauth": "charmlibs-interfaces-oauth",
    "openfga": "charmlibs-interfaces-openfga",
    "otlp": "charmlibs-interfaces-otlp",
    "service_mesh": "charmlibs-interfaces-service-mesh",
    "sloth": "charmlibs-interfaces-sloth",
    "tls_certificates": "charmlibs-interfaces-tls-certificates",
}

_IMPORT_RE = re.compile(r"from\s+charms\.(\w+)\.v\d+\.(\w+)")


def _resolve(prefix: str, submodule: str) -> tuple[str, str] | None:
    """Return ``(pypi_name, import_hint)`` for an import, or ``None``."""
    if prefix == "operator_libs_linux":
        if submodule in _OP_LIBS_LINUX_SUBMODULES:
            return (f"charmlibs-{submodule}", f"from charmlibs import {submodule}")
        return None
    pypi_name = _INTERFACE_LIBS.get(submodule)
    if pypi_name is None:
        return None
    return (pypi_name, f"from charmlibs.interfaces import {submodule}")


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
