"""Library rules — vendored fetch-libs copies with PyPI replacements."""

from .. import _models as models
from ._base import Rule

# Two families of `charmcraft fetch-lib` vendored libraries have known
# PyPI replacements:
#
# 1. `lib/charms/operator_libs_linux/vN/<submodule>.py` — each
#    submodule ships as its own `charmlibs-<submodule>` package.
# 2. `lib/charms/<owner>/vN/<lib>.py` — a shared interface library.
#    The `<owner>` charm varies by lib (tls-certificates-interface,
#    hydra-operator, traefik-k8s, …), so we match on the `<lib>`
#    module name — that's the interface-contract identity, and it's
#    stable across owners.
#
# Both tables are refreshed against
# https://canonical.com/juju/docs/charmlibs/reference/charmlibs-interfaces/
# and pypi.org/simple/. `tools/refresh_charmlibs_map.py` lists the
# live namespace.

_OP_LIBS_LINUX_SUBMODULES: frozenset[str] = frozenset(
    {"apt", "passwd", "snap", "sysctl", "systemd"}
)

# `<lib module>` → PyPI name for charmlibs-interfaces-*.
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


def _resolve(owner: str, lib: str) -> str | None:
    """Return the PyPI package name for a vendored lib, or ``None``."""
    if owner == "operator_libs_linux":
        if lib in _OP_LIBS_LINUX_SUBMODULES:
            return f"charmlibs-{lib}"
        return None
    return _INTERFACE_LIBS.get(lib)


class FetchLibsHasPyPI(Rule):
    """Detect vendored fetch-libs copies that have PyPI replacements."""

    category = "LIBRARY"
    number = 1
    name = "fetch-libs-has-pypi"
    description = "Deprecated Charmhub library has PyPI replacement"
    default_severity = models.Severity.WARNING
    reference_url = "https://canonical.com/juju/docs/charmlibs/"

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        # `charmcraft fetch-lib` writes to `lib/charms/<owner>/vN/<lib>.py`.
        # Walk that tree instead of parsing imports: it's the artefact
        # the user needs to delete, and it works even when the vendored
        # copy is no longer referenced from src/.
        charms_root = context.charm_dir / "lib" / "charms"
        if not charms_root.is_dir():
            return []

        diagnostics: list[models.Diagnostic] = []
        for owner_dir in sorted(charms_root.iterdir()):
            if not owner_dir.is_dir():
                continue
            owner = owner_dir.name
            for version_dir in sorted(owner_dir.iterdir()):
                if not (version_dir.is_dir() and version_dir.name.startswith("v")):
                    continue
                for lib_file in sorted(version_dir.glob("*.py")):
                    lib = lib_file.stem
                    pypi_name = _resolve(owner, lib)
                    if pypi_name is None:
                        continue
                    diagnostics.append(
                        self.diagnostic(
                            (
                                f"Vendored charm library {owner}.{version_dir.name}.{lib} "
                                f"has a PyPI replacement: {pypi_name}"
                            ),
                            path=str(lib_file),
                            fix_hint=(
                                f"delete this file and add '{pypi_name}' to your "
                                f"dependencies (for example: uv add {pypi_name})"
                            ),
                        )
                    )
        return diagnostics
