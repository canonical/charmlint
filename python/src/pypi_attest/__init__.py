"""PEP 740 attestation checks against the PyPI simple API.

A small, dependency-free helper shared by ``charmlint`` and ``quickpack``.
It answers one question per package: does PyPI hold a verified provenance
attestation for this distribution?

We rely on PyPI's simple-index v1 JSON, which exposes a ``provenance`` URL
for each file that was uploaded with a PEP 740 attestation validated by
PyPI.  Existence of that URL is treated as "attested"; absence means
either the project opted out of attestations or the upload pre-dated
PEP 740 support.

This module never downloads or cryptographically re-verifies the
attestation; for that, see the upstream ``pypi-attestations`` CLI.  The
goal here is a fast, check-at-build-time signal that deters unsigned
dependencies in the hot paths where Cantrip packs charms.

Must-have packages
------------------

Some packages are known to publish attestations via trusted publishers
(Canonical's GitHub Actions for ops/ops-scenario/ops-tracing/jubilant,
and the ``charmlibs-*`` namespace).  These are treated as hard failures
when unattested so that a misconfigured mirror, a typosquat, or a
compromised upload path is caught immediately.
"""

import dataclasses
import enum
import json
import re
import threading
import urllib.error
import urllib.request

# ---------------------------------------------------------------------------
# Name normalisation and must-have matching
# ---------------------------------------------------------------------------

_NORMALISE_RE = re.compile(r"[-_.]+")

# Patterns use PEP-503-normalised names (lower-case, ``-`` separated).
# A trailing ``-*`` is a prefix wildcard; otherwise exact match.
MUST_HAVE_PATTERNS: tuple[str, ...] = (
    "ops",
    "ops-scenario",
    "ops-tracing",
    "jubilant",
    "charmlibs-*",
)


def normalise_name(name: str) -> str:
    """Normalise a distribution name per PEP 503.

    Lower-cases the name and collapses any run of ``-``, ``_`` or ``.``
    into a single ``-``.  This is what PyPI uses as a cache key for its
    simple API, so every lookup must go through it.
    """
    return _NORMALISE_RE.sub("-", name.strip().lower())


def is_must_have(name: str) -> bool:
    """Return True if *name* is one of the packages we require to be attested."""
    normalised = normalise_name(name)
    for pattern in MUST_HAVE_PATTERNS:
        if pattern.endswith("-*"):
            if normalised.startswith(pattern[:-1]):
                return True
        elif normalised == pattern:
            return True
    return False


# ---------------------------------------------------------------------------
# PyPI simple-API provenance check
# ---------------------------------------------------------------------------


class ProvenanceStatus(enum.StrEnum):
    """Outcome of a single provenance check."""

    ATTESTED = "attested"
    UNATTESTED = "unattested"
    UNKNOWN = "unknown"  # Network error, PyPI 404, or response parse error.


@dataclasses.dataclass(frozen=True)
class ProvenanceResult:
    """Details returned alongside a ProvenanceStatus."""

    name: str
    status: ProvenanceStatus
    version: str | None = None  # Version we actually consulted (latest if unspecified).
    provenance_url: str | None = None
    detail: str | None = None  # Free-text reason for UNKNOWN / UNATTESTED.


# Process-wide cache keyed by (normalised name, version or None).  Avoids
# hammering PyPI when a single lint run inspects many dependencies, and
# makes tests easier to reason about.  Threading lock guards re-entry
# from parallel callers (charmlint rules are serial today, but we do not
# want a future parallel driver to double-fetch).
_CACHE: dict[tuple[str, str | None], ProvenanceResult] = {}
_CACHE_LOCK = threading.Lock()

_SIMPLE_API_BASE = "https://pypi.org/simple/"
_ACCEPT = "application/vnd.pypi.simple.v1+json"


def check_provenance(
    name: str,
    version: str | None = None,
    *,
    timeout: float = 5.0,
) -> ProvenanceResult:
    """Check whether PyPI has a provenance attestation for *name* (and *version*).

    If *version* is None, picks any file under the latest version present
    in the simple-index response.  Network or parse failures return
    :attr:`ProvenanceStatus.UNKNOWN` so callers can fail-open on missing
    connectivity without aborting the whole build.
    """
    key = (normalise_name(name), version)
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
    if cached is not None:
        return cached

    result = _check_provenance_uncached(name, version, timeout=timeout)
    with _CACHE_LOCK:
        _CACHE[key] = result
    return result


def clear_cache() -> None:
    """Reset the process-wide cache — only useful in tests."""
    with _CACHE_LOCK:
        _CACHE.clear()


def _check_provenance_uncached(
    name: str,
    version: str | None,
    *,
    timeout: float,
) -> ProvenanceResult:
    normalised = normalise_name(name)
    url = f"{_SIMPLE_API_BASE}{normalised}/"
    request = urllib.request.Request(url, headers={"Accept": _ACCEPT})

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            body = response.read()
    except urllib.error.HTTPError as exc:
        detail = f"PyPI returned HTTP {exc.code} for {normalised}"
        return ProvenanceResult(
            name=normalised, status=ProvenanceStatus.UNKNOWN, version=version, detail=detail
        )
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return ProvenanceResult(
            name=normalised,
            status=ProvenanceStatus.UNKNOWN,
            version=version,
            detail=f"network error: {exc}",
        )

    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        return ProvenanceResult(
            name=normalised,
            status=ProvenanceStatus.UNKNOWN,
            version=version,
            detail=f"invalid JSON from PyPI: {exc}",
        )

    files = data.get("files")
    if not isinstance(files, list) or not files:
        return ProvenanceResult(
            name=normalised,
            status=ProvenanceStatus.UNKNOWN,
            version=version,
            detail="no files in PyPI response",
        )

    candidates = _files_for_version(files, version)
    if not candidates:
        return ProvenanceResult(
            name=normalised,
            status=ProvenanceStatus.UNKNOWN,
            version=version,
            detail=f"version {version!r} not found on PyPI" if version else "no release files",
        )

    # If any candidate file carries a provenance URL, the release is attested.
    for entry in candidates:
        prov = entry.get("provenance")
        if isinstance(prov, str) and prov:
            return ProvenanceResult(
                name=normalised,
                status=ProvenanceStatus.ATTESTED,
                version=version or _infer_version(entry.get("filename", "")),
                provenance_url=prov,
            )

    return ProvenanceResult(
        name=normalised,
        status=ProvenanceStatus.UNATTESTED,
        version=version or _infer_version(candidates[-1].get("filename", "")),
        detail="no PEP 740 attestations on PyPI for this release",
    )


def _files_for_version(files: list[dict], version: str | None) -> list[dict]:
    """Return the subset of *files* that match *version* (or the last release)."""
    if version is None:
        return files

    matching = [f for f in files if _file_matches_version(f.get("filename", ""), version)]
    return matching


_FILENAME_VERSION_RE = re.compile(
    r"^(?P<name>[A-Za-z0-9_.-]+?)-(?P<version>\d[^-]*?)"
    r"(?:-(?:py|cp|pp|ip)\d|\.tar\.gz|\.zip|-\d+)"
)


def _infer_version(filename: str) -> str | None:
    """Pull the version portion out of a PyPI filename, if possible."""
    match = _FILENAME_VERSION_RE.match(filename)
    if match:
        return match.group("version")
    return None


def _file_matches_version(filename: str, version: str) -> bool:
    """Return True if *filename* encodes *version* (wheel or sdist)."""
    inferred = _infer_version(filename)
    if inferred is None:
        return False
    return inferred == version
