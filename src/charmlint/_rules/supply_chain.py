"""Supply chain rules — provenance of the artifacts a charm ships.

A charm's source is only half of what gets deployed: the OCI images it
declares as resources are built and published separately. These rules
check that the metadata records where those artifacts come from.
"""

import pathlib

from .. import _models as models
from .. import _yaml
from ._base import Rule

_IMAGE_SUFFIXES = ("-image", "_image")


def _normalise(name: object) -> str:
    """Fold a rock, directory, or resource name to one comparable form."""
    return str(name).replace("_", "-").lower()


def _locally_built_images(charm_dir: pathlib.Path) -> set[str]:
    """Return the names of images this repository builds for itself.

    A rock or Dockerfile in the charm directory, or up to two levels
    below it, names an image the charm's own CI builds and uploads. The
    candidate names are the rock's declared ``name`` and the directory
    holding the build recipe, since the ``foo_rock/``, ``rock/`` and
    ``foo_rocks/<component>/`` layouts are all common.
    """
    names: set[str] = set()
    for depth in ("", "*/", "*/*/"):
        for rockcraft in charm_dir.glob(f"{depth}rockcraft.yaml"):
            try:
                declared = _yaml.load(rockcraft).get("name")
            except _yaml.FileLoadError:
                declared = models.Yaml.absent(rockcraft.name)
            if isinstance(declared.value, str):
                names.add(_normalise(declared.value))
            names.add(
                _normalise(rockcraft.parent.name.removesuffix("_rock").removesuffix("-rock"))
            )
        for dockerfile in charm_dir.glob(f"{depth}Dockerfile"):
            names.add(_normalise(dockerfile.parent.name))
    return names


class OciImageMissingUpstreamSource(Rule):
    """Flag an ``oci-image`` resource with no ``upstream-source``."""

    category = "SUPPLYCHAIN"
    number = 1
    name = "oci-image-missing-upstream-source"
    description = "oci-image resource declared without an 'upstream-source'"
    default_severity = models.Severity.INFO
    reference_url = "https://canonical.com/juju/docs/charmcraft/stable/reference/files/charmcraft-yaml-file/#charmcraft-yaml-key-resources"

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        candidates = [
            (name, resource)
            for name, resource in context.metadata.get("resources").items()
            if resource.get("type").value == "oci-image" and not resource.get("upstream-source")
        ]
        if not candidates:
            return []

        # `upstream-source` names the image the resource is built from, so
        # it has nothing to say about an image this repository builds
        # itself: for those the build recipe is the record of provenance.
        local = _locally_built_images(context.charm_dir)
        diagnostics: list[models.Diagnostic] = []
        for name, resource in candidates:
            stem = _normalise(name)
            for suffix in _IMAGE_SUFFIXES:
                stem = stem.removesuffix(suffix)
            if stem in local or _normalise(name) in local:
                continue
            diagnostics.append(
                self.diagnostic(
                    f"OCI image resource '{name}' has no 'upstream-source', so there is "
                    "no record of which image it is built from",
                    # A split-metadata charm can declare `resources` in
                    # metadata.yaml, where the diagnostic — and any noqa
                    # silencing it — then belongs.
                    path=resource.source,
                    line=resource.line,
                    fix_hint=(
                        f"Add 'upstream-source' under resources.{name}, naming the image "
                        "the resource is built from (e.g. 'ghcr.io/canonical/foo:1.2.3')"
                    ),
                )
            )
        return diagnostics
