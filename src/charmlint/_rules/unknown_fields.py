"""Unknown-field detection — flags unrecognised keys in charmcraft.yaml / metadata.yaml.

Catches typos like ``sumary`` instead of ``summary`` that would otherwise
go silently unnoticed. Only top-level keys are checked; user-defined
sub-keys inside ``config.options``, ``actions``, ``requires``, etc. are
left alone because their names are charm-specific.

Two separate known-field sets are maintained because charmcraft.yaml and
metadata.yaml have different valid top-level keys (e.g. charmcraft.yaml uses
``title`` and a nested ``links`` block, while metadata.yaml uses
``display-name`` and top-level ``docs``/``issues``/``source``/``website``).
"""

from typing import Any

from .. import _models as models
from . import Rule

# Top-level keys valid in charmcraft.yaml (modern and legacy forms).
# Kept deliberately broad — a false positive on a genuine field is far
# worse than missing a truly unknown one.
_KNOWN_CHARMCRAFT_FIELDS: frozenset[str] = frozenset(
    {
        # Identity / metadata.
        "name",
        "type",
        "title",
        "summary",
        "description",
        # Build / platform.
        "base",
        "build-base",
        "bases",
        "platforms",
        "parts",
        "extensions",
        # Relations.
        "requires",
        "provides",
        "peers",
        "extra-bindings",
        # Config / actions.
        "config",
        "actions",
        # Workload.
        "containers",
        "resources",
        "storage",
        "devices",
        # Charm libraries and dependencies.
        "charm-libs",
        # Links block (Charmhub) — nested form, e.g. links.documentation.
        "links",
        # Legacy top-level contact (now links.contact).
        "contact",
        # Subordinate / assumes.
        "subordinate",
        "assumes",
        "terms",
        # Legacy (deprecated but still accepted).
        "series",
        "min-juju-version",
        # Analysis / linting config inside the file.
        "analysis",
    }
)

# Top-level keys valid in metadata.yaml (the separate legacy metadata file).
# metadata.yaml uses flat top-level link fields instead of a nested links block,
# and display-name/maintainers instead of title/links.contact.
_KNOWN_METADATA_FIELDS: frozenset[str] = frozenset(
    {
        # Identity / metadata.
        "name",
        "type",
        "display-name",
        "summary",
        "description",
        # Top-level link fields (metadata.yaml format, no nested links block).
        "docs",
        "issues",
        "source",
        "website",
        "maintainers",
        # Build / platform (bases was used in metadata.yaml before platforms).
        "bases",
        # Relations.
        "requires",
        "provides",
        "peers",
        "extra-bindings",
        # Config / actions.
        "config",
        "actions",
        # Workload.
        "containers",
        "resources",
        "storage",
        "devices",
        # Subordinate / assumes.
        "subordinate",
        "assumes",
        "terms",
        # Legacy (deprecated but still accepted).
        "series",
        "min-juju-version",
    }
)

# Keys recognised inside a ``resources.<name>`` block.
_KNOWN_RESOURCE_FIELDS: frozenset[str] = frozenset(
    {
        "type",
        "description",
        "filename",
        "upstream-source",
    }
)


class UnknownTopLevelFields(Rule):
    """Flag unrecognised top-level keys in charmcraft.yaml or metadata.yaml."""

    id = "CC005"
    name = "unknown-top-level-field"
    description = "Unrecognised top-level field in charm metadata (possible typo)"
    default_severity = models.Severity.WARNING

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        known = (
            _KNOWN_METADATA_FIELDS
            if context.metadata_source == "metadata.yaml"
            else _KNOWN_CHARMCRAFT_FIELDS
        )
        diagnostics: list[models.Diagnostic] = []
        for key in context.metadata:
            if key not in known:
                diagnostics.append(
                    self.diagnostic(
                        f"Unrecognised top-level field '{key}' in {context.metadata_source} — possible typo",
                        path=context.metadata_source,
                        fix_hint=_suggest_closest(key, known),
                    )
                )
        return diagnostics


class UnknownResourceFields(Rule):
    """Flag unrecognised keys inside resource definitions."""

    id = "CC006"
    name = "unknown-resource-field"
    description = "Unrecognised field inside a resource definition (possible typo)"
    default_severity = models.Severity.WARNING

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        resources: dict[str, Any] = context.metadata.get("resources", {})
        if not isinstance(resources, dict):
            return []

        diagnostics: list[models.Diagnostic] = []
        for res_name, res_def in resources.items():
            if not isinstance(res_def, dict):
                continue
            for key in res_def:
                if key not in _KNOWN_RESOURCE_FIELDS:
                    diagnostics.append(
                        self.diagnostic(
                            f"Unrecognised field '{key}' in resource '{res_name}' — possible typo",
                            path=context.metadata_source,
                            fix_hint=_suggest_closest(key, _KNOWN_RESOURCE_FIELDS),
                        )
                    )
        return diagnostics


def _suggest_closest(typo: str, known: frozenset[str]) -> str | None:
    """Return a ``Did you mean 'X'?`` hint if a close match exists."""
    best: str | None = None
    best_dist = 3  # Only suggest if edit distance <= 2.
    for candidate in known:
        d = _edit_distance(typo, candidate, best_dist)
        if d < best_dist:
            best_dist = d
            best = candidate
    return f"Did you mean '{best}'?" if best else None


def _edit_distance(a: str, b: str, threshold: int) -> int:
    """Levenshtein distance, bailing out early if it exceeds *threshold*."""
    if abs(len(a) - len(b)) >= threshold:
        return threshold
    # Standard two-row DP.
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1] + [0] * len(b)
        for j, cb in enumerate(b):
            cost = 0 if ca == cb else 1
            curr[j + 1] = min(prev[j + 1] + 1, curr[j] + 1, prev[j] + cost)
        prev = curr
    return prev[len(b)]
