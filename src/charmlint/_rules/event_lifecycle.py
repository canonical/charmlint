"""Event lifecycle completeness rules.

The contract: a non-optional ``requires:`` relation is part of the charm's
core dependency graph, so the charm needs to react when Juju tears that
relation down.  In practice that means observing
``self.on.<endpoint>_relation_broken`` — without it, cleanup logic is
skipped and the charm is left holding stale state.

EVNT001 walks every ``requires:`` entry where ``optional`` is not
``True`` (absence of the key counts as non-optional) and checks the
charm source for a matching ``framework.observe(...)`` call.  Endpoint
names with hyphens are normalised to underscores to match Juju's event
attribute naming.
"""

import pathlib
import re

from .. import models
from . import Rule


def _has_broken_observer(sources: dict[pathlib.Path, str], endpoint: str) -> bool:
    """True if some src/ file observes ``<endpoint>_relation_broken``."""
    normalised = endpoint.replace("-", "_")
    pattern = re.compile(r"observe\s*\([^)]*\b" + re.escape(normalised) + r"_relation_broken\b")
    for path, content in sources.items():
        if "lib" in path.parts:
            continue
        if pattern.search(content):
            return True
    return False


class NonOptionalRequiresWithoutBrokenObserver(Rule):
    """Flag non-optional requires endpoints with no relation-broken observer."""

    id = "EVNT001"
    name = "non-optional-requires-without-broken-observer"
    description = "Non-optional requires endpoint has no relation-broken event observer"
    default_severity = models.Severity.WARNING

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        requires = context.metadata.get("requires", {})
        if not isinstance(requires, dict):
            return diagnostics
        for endpoint, definition in requires.items():
            optional = False
            if isinstance(definition, dict):
                optional = definition.get("optional") is True
            if optional:
                continue
            if _has_broken_observer(context.python_sources, endpoint):
                continue
            normalised = endpoint.replace("-", "_")
            diagnostics.append(
                self.diagnostic(
                    f"Non-optional requires endpoint '{endpoint}' has no "
                    f"framework.observe(self.on.{normalised}_relation_broken, "
                    "...) — relation teardown will not be handled",
                    path="charmcraft.yaml",
                    fix_hint=(
                        f"Observe self.on.{normalised}_relation_broken to "
                        "clean up state, or mark the endpoint `optional: true` "
                        "in charmcraft.yaml"
                    ),
                )
            )
        return diagnostics
