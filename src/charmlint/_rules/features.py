"""Features rules — capabilities a charm is expected to declare.

These rules are about what the charm tells Juju it needs, rather than
about what its Python does. A charm that relies on a feature Juju only
added in a recent release has no way to refuse an older controller
unless it says so in its metadata.
"""

from .. import _models as models
from ._base import Rule

# `assumes` entries nest: a group is a single-key mapping whose value is
# the list of nested entries. Both quantifiers are valid at any depth.
_GROUP_KEYS = ("any-of", "all-of")


def _is_juju_entry(entry: models.Yaml) -> bool:
    """Report whether *entry* is a `juju` feature expression.

    Both structures mean the same thing to Juju: the flat string form
    (``juju >= 3.6``) and the mapping form (``{juju: ">= 3.6"}``). In
    either form, a bare ``juju`` with nothing after it is not a version
    constraint, so it does not count.
    """
    value = entry.value
    if isinstance(value, str):
        head, _, rest = value.strip().partition(" ")
        return head.lower() == "juju" and bool(rest.strip())
    if isinstance(value, dict):
        return any(
            isinstance(key, str)
            and key.strip().lower() == "juju"
            and isinstance(val, str)
            and bool(val.strip())
            for key, val in value.items()
        )
    return False


def _has_juju_constraint(assumes: models.Yaml) -> bool:
    """Report whether *assumes* declares a Juju version anywhere inside it.

    A charm may put the constraint inside an ``any-of`` / ``all-of``
    group rather than at the top level. Either way the charm has thought
    about the version, which is all this rule asks for.
    """
    for entry in assumes.elements or ():
        if _is_juju_entry(entry):
            return True
        for key in _GROUP_KEYS:
            if key in entry and _has_juju_constraint(entry.get(key)):
                return True
    return False


class NoAssumesJujuVersion(Rule):
    category = "FEATURES"
    number = 4
    name = "no-assumes-juju-version"
    description = "No `assumes:` entry declaring a minimum Juju version"
    default_severity = models.Severity.INFO
    reference_url = "https://canonical.com/juju/docs/charmcraft/stable/reference/files/charmcraft-yaml-file/#charmcraft-yaml-key-assumes"

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        # A bundle has no `assumes`; the key is charm metadata only.
        if context.metadata.get("type").value == "bundle":
            return []
        name = context.metadata.get("name")
        # Only charms that keep their metadata in charmcraft.yaml. A charm
        # still declaring `name` in metadata.yaml predates the unified
        # file, and possibly predates `assumes` (Juju 2.9.23) as well.
        if not name.present or name.source != "charmcraft.yaml":
            return []
        assumes = context.metadata.get("assumes")
        if _has_juju_constraint(assumes):
            return []
        return [
            self.diagnostic(
                "No `assumes:` entry declaring a minimum Juju version — Juju cannot "
                "refuse to deploy the charm onto a controller too old for it",
                # An `assumes` block that exists but says nothing about the
                # Juju version is worth pointing at; an absent one has no
                # line to anchor to.
                path=assumes.source if assumes.present else context.metadata.source,
                line=assumes.line,
                fix_hint=(
                    "Add `assumes: [juju >= 3.6]`, naming the oldest Juju the charm supports"
                ),
            )
        ]
