"""Attestation rules — PEP 740 PyPI attestation checks for charm dependencies.

ATT001: a package on the "must-have attestations" list lacks PyPI provenance.
        Hard error, because these packages (ops, ops-scenario, ops-tracing,
        jubilant, charmlibs-*) are known to publish attestations through
        trusted publishers; an unattested file is a supply-chain red flag.

ATT002: a non-must-have dependency lacks provenance.  Informational by
        default; the ecosystem is still catching up, so we nudge rather
        than block.

Both rules parse ``pyproject.toml`` ``[project].dependencies`` and any
``requirements.txt`` sitting alongside the charm.  Network failures and
other PyPI hiccups are treated as silent so linting fails open on an
offline host rather than crying wolf.
"""

import pathlib
import re
import tomllib

import pypi_attest

from .. import models
from . import Rule

# ---------------------------------------------------------------------------
# Dependency extraction
# ---------------------------------------------------------------------------

# PEP 508 parsing is heavy; for lint purposes we only need the project name
# (and, when an exact pin is given, the version).  Anything more exotic is
# accepted as "name only" — the subsequent PyPI lookup works off the latest
# release, which is the right behaviour when the user hasn't pinned.
_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9_.\-]*)")
_EXACT_VERSION_RE = re.compile(r"==\s*([A-Za-z0-9_.\-+!]+)")


def _parse_requirement(line: str) -> tuple[str, str | None] | None:
    """Return ``(name, version_or_None)`` for a PEP 508 requirement string."""
    stripped = line.split("#", 1)[0].strip()
    if not stripped or stripped.startswith("-"):
        # Skip blank lines, comments, and pip flags like ``-r other.txt``.
        return None

    name_match = _NAME_RE.match(stripped)
    if name_match is None:
        return None

    name = name_match.group(1)
    version_match = _EXACT_VERSION_RE.search(stripped)
    version = version_match.group(1) if version_match else None
    return name, version


def _extract_dependencies(charm_dir: pathlib.Path) -> list[tuple[str, str | None, str]]:
    """Collect ``(name, version, source_path)`` for each dependency.

    Reads ``pyproject.toml`` ``[project].dependencies`` and
    ``requirements.txt`` if present.  Duplicate names across both files
    are kept once (pyproject.toml wins for version information).
    """
    seen: dict[str, tuple[str, str | None, str]] = {}

    pyproject = charm_dir / "pyproject.toml"
    if pyproject.is_file():
        try:
            data = tomllib.loads(pyproject.read_text())
        except (OSError, tomllib.TOMLDecodeError):
            data = {}
        deps = data.get("project", {}).get("dependencies", [])
        if isinstance(deps, list):
            for raw in deps:
                if not isinstance(raw, str):
                    continue
                parsed = _parse_requirement(raw)
                if parsed is None:
                    continue
                name, version = parsed
                key = pypi_attest.normalise_name(name)
                seen.setdefault(key, (name, version, str(pyproject)))

    requirements = charm_dir / "requirements.txt"
    if requirements.is_file():
        try:
            lines = requirements.read_text().splitlines()
        except OSError:
            lines = []
        for raw in lines:
            parsed = _parse_requirement(raw)
            if parsed is None:
                continue
            name, version = parsed
            key = pypi_attest.normalise_name(name)
            if key not in seen:
                seen[key] = (name, version, str(requirements))

    return list(seen.values())


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


class MustHaveAttestationsMissing(Rule):
    """A must-have package is missing a PyPI attestation."""

    id = "ATT001"
    name = "must-have-package-unattested"
    description = "Dependency must have a PyPI attestation but PyPI reports none for this release."
    default_severity = models.Severity.ERROR

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        return _run_checks(self, context, only_must_have=True)


class DependencyMissingAttestation(Rule):
    """A dependency is missing a PyPI attestation (advisory)."""

    id = "ATT002"
    name = "dependency-unattested"
    description = "Dependency release has no PEP 740 attestation on PyPI."
    default_severity = models.Severity.INFO

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        return _run_checks(self, context, only_must_have=False)


def _run_checks(
    rule: Rule,
    context: models.CharmContext,
    *,
    only_must_have: bool,
) -> list[models.Diagnostic]:
    """Shared driver for ATT001 / ATT002.

    ``only_must_have=True`` emits diagnostics for must-have packages only.
    ``only_must_have=False`` skips must-haves (ATT001 already owns those)
    and emits for everything else whose PyPI release has no attestation.
    Both paths treat ``UNKNOWN`` (network/PyPI error) as silent so we do
    not cry wolf when the charm is being linted offline.
    """
    diagnostics: list[models.Diagnostic] = []
    for name, version, source in _extract_dependencies(context.charm_dir):
        must_have = pypi_attest.is_must_have(name)
        if only_must_have and not must_have:
            continue
        if not only_must_have and must_have:
            continue

        result = pypi_attest.check_provenance(name, version)
        if result.status is not pypi_attest.ProvenanceStatus.UNATTESTED:
            continue

        version_str = f"=={version}" if version else ""
        message = (
            f"{name}{version_str} has no PyPI attestation "
            f"(expected for {name}; see https://peps.python.org/pep-0740/)"
            if only_must_have
            else f"{name}{version_str} has no PyPI attestation"
        )
        diagnostics.append(
            rule.diagnostic(
                message,
                path=source,
                fix_hint=(
                    f"Confirm publisher provenance on https://pypi.org/project/"
                    f"{pypi_attest.normalise_name(name)}/"
                ),
            )
        )
    return diagnostics
