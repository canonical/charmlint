"""Charmcraft-compatible rules — checks that mirror ``charmcraft analyse``."""

import os
import pathlib
import re

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
        series = context.metadata.get("series")
        if not series.present:
            return []
        return [
            self.diagnostic(
                "'series' is deprecated in charm metadata — use 'bases' or 'platforms' instead",
                path=series.source,
                line=series.line,
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
        for opt_name, option in context.config_options.items():
            if isinstance(opt_name, str) and "_" in opt_name:
                hyphenated = re.sub(r"[-_]+", "-", opt_name)
                diagnostics.append(
                    self.diagnostic(
                        f"Config option '{opt_name}' uses underscores — prefer hyphens ('{hyphenated}')",
                        path=option.source,
                        line=option.line,
                        fix_hint=f"Rename to '{hyphenated}'",
                    )
                )
        return diagnostics


class Entrypoint(Rule):
    category = "CHARMCRAFT"
    number = 3
    name = "dispatch-entrypoint-issues"
    description = "Charm entrypoint missing or not executable"
    default_severity = models.Severity.ERROR
    reference_url = (
        "https://canonical.com/juju/docs/charmcraft/stable/reference/files/dispatch-file/"
    )

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        # charmcraft generates dispatch at pack time, so most charm repos do
        # not have one. Only a hand-written dispatch is worth checking.
        dispatch = context.charm_dir / "dispatch"
        if not dispatch.is_file():
            return []
        try:
            # Decoding never fails (errors="replace"), so this is only the
            # environmental cases — unreadable mode, I/O error — where the
            # charm itself is not at fault.
            content = dispatch.read_text(errors="replace")
        except OSError:
            return []

        resolved = self._entrypoint(content)
        if resolved is None:
            return []
        entrypoint_rel, via_interpreter = resolved
        entrypoint = context.charm_dir / entrypoint_rel

        if not entrypoint.exists():
            return [
                self.diagnostic(
                    f"Entrypoint '{entrypoint_rel}' referenced in dispatch does not exist",
                    path="dispatch",
                    fix_hint=f"Create {entrypoint_rel}, or point dispatch at the real entrypoint",
                )
            ]
        if not entrypoint.is_file():
            return [
                self.diagnostic(
                    f"Entrypoint '{entrypoint_rel}' referenced in dispatch is not a regular file",
                    path="dispatch",
                )
            ]
        # An entrypoint handed to an interpreter does not need the executable
        # bit — only one dispatch runs directly does.
        if not via_interpreter and not os.access(entrypoint, os.X_OK):
            return [
                self.diagnostic(
                    f"Entrypoint '{entrypoint_rel}' is not executable",
                    path=entrypoint_rel,
                    fix_hint=f"Run: chmod +x {entrypoint_rel}",
                )
            ]
        return []

    def _entrypoint(self, dispatch_content: str) -> tuple[str, bool] | None:
        """Resolve the entrypoint dispatch runs.

        Returns the charm-relative path and whether it is handed to an
        interpreter rather than executed directly, or ``None`` when dispatch
        does something too dynamic to resolve statically.
        """
        command_line = self._command_line(dispatch_content)
        if command_line is None:
            return None

        via_interpreter = False
        words = [word.strip("'\"") for word in command_line.split()]
        for index, word in enumerate(words):
            more_follow = index < len(words) - 1
            # A leading ``VAR=`` assignment, e.g. ``PYTHONPATH=lib:venv``.
            if re.match(r"^\w+=", word):
                continue
            # An interpreter run by name: ``python``, ``python3``,
            # ``python3.12``, or ``/usr/bin/env`` (matched on basename).
            if more_follow and re.match(
                r"^(?:python[0-9.]*|env)$", pathlib.PurePosixPath(word).name
            ):
                via_interpreter = True
                continue
            # An interpreter named by a variable, e.g. ``$PYTHON_BIN charm.py``:
            # unresolvable as a command, but its argument is still the charm.
            if more_follow and "$" in word:
                via_interpreter = True
                continue
            relative = self._charm_relative(word)
            return None if relative is None else (relative, via_interpreter)
        return None

    def _command_line(self, dispatch_content: str) -> str | None:
        """Return the dispatch line that runs the charm, sans any ``exec``."""
        # The command dispatch hands control to, e.g. the ``./src/charm.py``
        # in ``PYTHONPATH=lib:venv exec ./src/charm.py``. Stops at a shell
        # separator so a trailing redirect or ``&&`` is not swallowed in.
        match = re.search(r"\bexec\s+(?P<rest>[^\n;&|<>]+)", dispatch_content)
        if match is not None:
            return match.group("rest")
        # No ``exec``: hand-written dispatch scripts often just run the charm
        # as their last statement. Only the last statement is considered, so a
        # ``.py`` path mentioned earlier in the script is not mistaken for the
        # entrypoint.
        for line in reversed(dispatch_content.splitlines()):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            return line if ".py" in line else None
        return None

    def _charm_relative(self, command: str) -> str | None:
        """Normalise a dispatch command to a charm-relative path, if it is one."""
        # Anything with shell expansion in it, or pointing outside the charm,
        # cannot be resolved statically.
        if not command or "$" in command or "`" in command:
            return None
        path = pathlib.PurePosixPath(command)
        if path.is_absolute() or ".." in path.parts:
            return None
        parts = [part for part in path.parts if part != "."]
        return str(pathlib.PurePosixPath(*parts)) if parts else None


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
        for key, field in context.metadata.items():
            # A charm may split its metadata across both files, in which case
            # each key is judged against the set for the file it came from.
            source = field.source
            known = (
                _KNOWN_METADATA_FIELDS if source == "metadata.yaml" else _KNOWN_CHARMCRAFT_FIELDS
            )
            if key in known:
                continue
            # A key that is valid in the *other* file is a misplaced field
            # rather than a typo, and saying so is more useful than a
            # "did you mean" hint that has nothing close to suggest.
            other = (
                _KNOWN_CHARMCRAFT_FIELDS if source == "metadata.yaml" else _KNOWN_METADATA_FIELDS
            )
            if key in other:
                other_source = "charmcraft.yaml" if source == "metadata.yaml" else "metadata.yaml"
                message = f"Field '{key}' is valid in {other_source} but not {source}"
                fix_hint = None
            else:
                message = f"Unrecognised top-level field '{key}' in {source} — possible typo"
                fix_hint = _suggest_closest(key, known)
            diagnostics.append(
                self.diagnostic(
                    message,
                    path=source,
                    line=field.line,
                    fix_hint=fix_hint,
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
        diagnostics: list[models.Diagnostic] = []
        for res_name, resource in context.metadata.get("resources").items():
            for key, field in resource.items():
                if key not in _KNOWN_RESOURCE_FIELDS:
                    diagnostics.append(
                        self.diagnostic(
                            f"Unrecognised field '{key}' in resource '{res_name}' — possible typo",
                            path=field.source,
                            line=field.line,
                            fix_hint=_suggest_closest(key, _KNOWN_RESOURCE_FIELDS),
                        )
                    )
        return diagnostics


def _suggest_closest(typo: object, known: frozenset[str]) -> str | None:
    """Return a ``Did you mean 'X'?`` hint if a close match exists."""
    # YAML keys are not necessarily strings: an unquoted `on:` parses to a
    # bool, and a bare numeric key to an int. Those get flagged, but no hint.
    if not isinstance(typo, str):
        return None
    best: list[str] = []
    best_dist = 2  # Only suggest if edit distance <= 2.
    # Sorted so that equally-close candidates are listed in a stable order:
    # `known` is a frozenset, whose iteration order varies with PYTHONHASHSEED.
    for candidate in sorted(known):
        # `best_dist + 1` as the threshold, so that anything at or below
        # `best_dist` is an exact distance rather than an early bail-out.
        d = _edit_distance(typo, candidate, best_dist + 1)
        if d > best_dist:
            continue
        if d < best_dist:
            best_dist = d
            best = []
        best.append(candidate)
    if not best:
        return None
    quoted = [f"'{c}'" for c in best]
    if len(quoted) > 1:
        quoted[-1] = f"or {quoted[-1]}"
    joined = " ".join(quoted) if len(quoted) == 2 else ", ".join(quoted)
    return f"Did you mean {joined}?"


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
