"""JUJU rules — Juju-ness / idiomatic ops conventions."""

from .. import models
from . import Rule


class VendoredLibsNoCharmLibs(Rule):
    """Flag charms with vendored external libs but no ``charm-libs:`` declaration."""

    id = "JUJU006"
    name = "vendored-libs-no-charm-libs"
    description = "vendored charm libs present without `charm-libs:` declaration"
    default_severity = models.Severity.INFO

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []

        lib_charms_dir = context.charm_dir / "lib" / "charms"
        if not lib_charms_dir.is_dir():
            return diagnostics

        # The charm's own namespace under lib/charms/ uses underscores in
        # place of hyphens in the metadata name.
        own_name = context.metadata.get("name")
        own_namespace = own_name.replace("-", "_") if isinstance(own_name, str) else None

        has_external = False
        for child in lib_charms_dir.iterdir():
            if not child.is_dir():
                continue
            if own_namespace is not None and child.name == own_namespace:
                continue
            # Look for any .py file under lib/charms/<ext>/v*/.
            for version_dir in child.iterdir():
                if not version_dir.is_dir() or not version_dir.name.startswith("v"):
                    continue
                if any(p.suffix == ".py" for p in version_dir.iterdir() if p.is_file()):
                    has_external = True
                    break
            if has_external:
                break

        if not has_external:
            return diagnostics

        if "charm-libs" in context.metadata:
            return diagnostics

        diagnostics.append(
            self.diagnostic(
                "vendored external charm libraries found under `lib/charms/` "
                "but `charmcraft.yaml` has no `charm-libs:` declaration — "
                "without it, `charmcraft fetch-libs` cannot update vendored "
                "libraries reproducibly",
                path="charmcraft.yaml",
                fix_hint=(
                    "Add a `charm-libs:` section to `charmcraft.yaml` listing the "
                    "vendored libraries (each entry: `lib: <charm>.<library>`, "
                    '`version: "<api>"`)'
                ),
            )
        )
        return diagnostics
