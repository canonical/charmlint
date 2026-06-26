"""Attestation rules — PEP 740 PyPI attestation checks for charm dependencies.

Module scaffolding lands first (dependency extraction + shared driver);
ATT001 and ATT002 each follow in their own PR with just the rule class.
"""

import pathlib
import re
import tomllib

from .. import _models as models
from .. import _pypi_attest as pypi_attest
from . import Rule

_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9_.\-]*)")
_EXACT_VERSION_RE = re.compile(r"==\s*([A-Za-z0-9_.\-+!]+)")


def _parse_requirement(line: str) -> tuple[str, str | None] | None:
    """Return ``(name, version_or_None)`` for a PEP 508 requirement string."""
    stripped = line.split("#", 1)[0].strip()
    if not stripped or stripped.startswith("-"):
        return None

    name_match = _NAME_RE.match(stripped)
    if name_match is None:
        return None

    name = name_match.group(1)
    version_match = _EXACT_VERSION_RE.search(stripped)
    version = version_match.group(1) if version_match else None
    return name, version


def _extract_dependencies(charm_dir: pathlib.Path) -> list[tuple[str, str | None, str]]:
    """Collect ``(name, version, source_path)`` for each dependency."""
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


def _run_checks(
    rule: Rule,
    context: models.CharmContext,
    *,
    only_must_have: bool,
) -> list[models.Diagnostic]:
    """Shared driver for ATT001 / ATT002.

    Treats ``UNKNOWN`` (network/PyPI error) as silent so we do not cry wolf
    when the charm is being linted offline.
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
