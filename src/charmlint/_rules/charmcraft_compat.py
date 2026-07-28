"""Charmcraft-compatible rules — checks that mirror ``charmcraft analyse``."""

import re
from typing import Any

from .. import _models as models
from ._base import Rule

# Top-level keys valid in charmcraft.yaml (modern and legacy forms). A
# separate set is kept for metadata.yaml below, because the two files accept
# different top-level keys.
# Kept deliberately broad — a false positive on a genuine field is far
# worse than missing a truly unknown one.
# The modern keys mirror charmcraft's published schema/charmcraft.json, plus
# legacy keys the schema has dropped. Hand-maintained for now; see #174 for
# validating against that schema directly instead.
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
        "adopt-info",
        "package-repositories",
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
        # Workload run-as user (Kubernetes charms).
        "charm-user",
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
        "charmhub",
        # Analysis / linting config inside the file.
        "analysis",
    }
)

# Keys that configure how the charm is *built*. These are meaningful only in
# charmcraft.yaml, so they stay unknown in metadata.yaml.
_BUILD_ONLY_FIELDS: frozenset[str] = frozenset(
    {
        "parts",
        "base",
        "build-base",
        "extensions",
        "adopt-info",
        "package-repositories",
        "analysis",
        "charmhub",
    }
)

# Keys valid in metadata.yaml but not charmcraft.yaml. metadata.yaml uses flat
# top-level link fields instead of a nested links block, and
# display-name/maintainers instead of title/links.contact.
_METADATA_ONLY_FIELDS: frozenset[str] = frozenset(
    {
        "display-name",
        # Top-level link fields (no nested links block).
        "docs",
        "issues",
        "source",
        "website",
        # Both the list form and the singular string form are valid.
        "maintainers",
        "maintainer",
        # Charmhub categorisation ('categories' predates 'tags').
        "tags",
        "categories",
        # Kubernetes deployment block (type / service).
        "deployment",
        # Legacy (deprecated but still accepted).
        "format",
        "version",
    }
)

# Top-level keys valid in metadata.yaml (the separate legacy metadata file).
# Everything that describes the charm itself is valid in either file — a charm
# that splits its metadata may put those keys on either side — so only the
# build-only keys above are charmcraft.yaml-exclusive.
_KNOWN_METADATA_FIELDS: frozenset[str] = _METADATA_ONLY_FIELDS | (
    _KNOWN_CHARMCRAFT_FIELDS - _BUILD_ONLY_FIELDS
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


class DeprecatedSeries(Rule):
    category = "CHARMCRAFT"
    number = 1
    name = "deprecated-series"
    description = "Deprecated 'series' attribute in metadata"
    default_severity = models.Severity.WARNING
    reference_url = "https://canonical.com/juju/docs/charmcraft/stable/reference/files/charmcraft-yaml-file/#charmcraft-yaml-key-platforms"

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        if "series" not in context.metadata:
            return []
        return [
            self.diagnostic(
                "'series' is deprecated in charm metadata — use 'bases' or 'platforms' instead",
                path=_source_of(context, "series"),
                line=context.metadata_key_lines.get("series"),
                fix_hint="Remove 'series' and use 'bases' or 'platforms'",
            )
        ]


class NamingConventions(Rule):
    category = "CHARMCRAFT"
    number = 2
    name = "naming-conventions"
    description = "Config option names use underscores instead of hyphens"
    default_severity = models.Severity.WARNING
    reference_url = "https://canonical.com/juju/docs/charmcraft/stable/reference/files/charmcraft-yaml-file/#charmcraft-yaml-key-config"

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        # Juju/charmcraft reject underscored action names outright, and
        # underscored action parameters are vanishingly rare in the wild,
        # so this rule targets config options only.
        diagnostics: list[models.Diagnostic] = []
        for opt_name in context.config_options:
            if "_" in opt_name:
                hyphenated = re.sub(r"[-_]+", "-", opt_name)
                diagnostics.append(
                    self.diagnostic(
                        f"Config option '{opt_name}' uses underscores — prefer hyphens ('{hyphenated}')",
                        # Options may come from config.yaml rather than the
                        # metadata file, and the line is only meaningful
                        # against the file that declared them.
                        path=context.config_source,
                        line=context.config_option_lines.get(opt_name),
                        fix_hint=f"Rename to '{hyphenated}'",
                    )
                )
        return diagnostics


class UnknownTopLevelField(Rule):
    """Flag unrecognised top-level keys in charmcraft.yaml or metadata.yaml.

    Catches typos like ``sumary`` instead of ``summary`` that would otherwise
    go silently unnoticed. Only top-level keys are checked; user-defined
    sub-keys inside ``config.options``, ``actions``, ``requires``, etc. are
    left alone because their names are charm-specific.
    """

    category = "CHARMCRAFT"
    number = 4
    name = "unknown-top-level-field"
    description = "Unrecognised top-level field in charm metadata (possible typo)"
    default_severity = models.Severity.WARNING
    reference_url = (
        "https://canonical.com/juju/docs/charmcraft/stable/reference/files/charmcraft-yaml-file/"
    )

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        for key in context.metadata:
            # A charm may split its metadata across both files, in which case
            # each key is judged against the set for the file it came from.
            source = _source_of(context, key)
            known = (
                _KNOWN_METADATA_FIELDS if source == "metadata.yaml" else _KNOWN_CHARMCRAFT_FIELDS
            )
            if key not in known:
                diagnostics.append(
                    self.diagnostic(
                        f"Unrecognised top-level field '{key}' in {source} — possible typo",
                        path=source,
                        line=context.metadata_key_lines.get(key),
                        fix_hint=_suggest_closest(key, known),
                    )
                )
        return diagnostics


class UnknownResourceField(Rule):
    """Flag unrecognised keys inside resource definitions."""

    category = "CHARMCRAFT"
    number = 5
    name = "unknown-resource-field"
    description = "Unrecognised field inside a resource definition (possible typo)"
    default_severity = models.Severity.WARNING
    reference_url = "https://canonical.com/juju/docs/charmcraft/stable/reference/files/charmcraft-yaml-file/#charmcraft-yaml-key-resources"

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        resources: dict[str, Any] = context.metadata.get("resources", {})
        if not isinstance(resources, dict):
            return []

        source = _source_of(context, "resources")
        diagnostics: list[models.Diagnostic] = []
        for res_name, res_def in resources.items():
            if not isinstance(res_def, dict):
                continue
            for key in res_def:
                if key not in _KNOWN_RESOURCE_FIELDS:
                    diagnostics.append(
                        self.diagnostic(
                            f"Unrecognised field '{key}' in resource '{res_name}' — possible typo",
                            path=source,
                            line=context.resource_field_lines.get((res_name, key)),
                            fix_hint=_suggest_closest(key, _KNOWN_RESOURCE_FIELDS),
                        )
                    )
        return diagnostics


def _source_of(context: models.CharmContext, key: str) -> str:
    """Return the file a top-level metadata key was read from."""
    return context.metadata_key_sources.get(key, context.metadata_source)


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
