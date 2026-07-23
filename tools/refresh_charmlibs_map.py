"""Diff the live ``charmlibs-*`` PyPI namespace against LIBRARY-001's map.

Run this before releasing a new charmlint version to see whether the
``charmlibs-*`` packages on PyPI still line up with what LIBRARY-001
maps. It imports the rule's tables directly and reports two gaps:

* **stale mappings** — a PyPI name LIBRARY-001 recommends that no longer
  exists on PyPI (a genuine bug in the map);
* **unmapped packages** — ``charmlibs-*`` packages on PyPI that
  LIBRARY-001 doesn't map yet (candidates to add).

New general libraries (operator_libs_linux submodules, rollingops, …)
go into ``_GENERAL_LIBS``; new interface libs go into
``_INTERFACE_LIBS`` after confirming the
source-charm name in Charmhub (which is what the fetch-libs import path
uses). Unmapped packages need a human eye — the fetch-libs prefix isn't
derivable from the PyPI name — so this only lists them, it doesn't guess.

Usage:
    uv run python tools/refresh_charmlibs_map.py

Exits non-zero if any stale mapping is found.

Deliberately kept off the runtime path — LIBRARY-001 must stay offline.
"""

from __future__ import annotations

import re
import sys
import urllib.request

from charmlint._rules.libraries import _GENERAL_LIBS, _INTERFACE_LIBS

_SIMPLE_INDEX = "https://pypi.org/simple/"
_PACKAGE_RE = re.compile(r">(charmlibs[a-z0-9-]*)</a>")


def fetch_charmlibs() -> set[str]:
    with urllib.request.urlopen(_SIMPLE_INDEX, timeout=30) as response:
        body = response.read().decode("utf-8", errors="replace")
    return {m.group(1) for m in _PACKAGE_RE.finditer(body)}


def mapped_pypi_names() -> set[str]:
    """The set of PyPI package names LIBRARY-001 currently recommends."""
    return set(_GENERAL_LIBS.values()) | set(_INTERFACE_LIBS.values())


def main() -> int:
    live = fetch_charmlibs()
    if not live:
        print("no charmlibs-* packages found on PyPI", file=sys.stderr)
        return 1

    mapped = mapped_pypi_names()
    # The bare `charmlibs` umbrella package is never a fetch-lib target.
    candidates = live - mapped - {"charmlibs"}
    stale = mapped - live

    interfaces = sorted(p for p in candidates if p.startswith("charmlibs-interfaces-"))
    top_level = sorted(p for p in candidates if not p.startswith("charmlibs-interfaces-"))

    if stale:
        print("# STALE — mapped in LIBRARY-001 but no longer on PyPI (fix the map):")
        for name in sorted(stale):
            print(f"    {name}")
        print()

    print("# Unmapped charmlibs-* packages on PyPI (candidates for LIBRARY-001).")
    print("# The fetch-libs prefix isn't derivable from the PyPI name for interface")
    print("# libs — look up the owning charm on charmhub before adding a mapping.")
    print()
    print("# Top-level charmlibs (candidates for _GENERAL_LIBS if they have an")
    print("# old-style fetch-lib form; otherwise informational only):")
    for name in top_level:
        print(f"    {name}")
    print()
    print("# charmlibs-interfaces-* (candidates for _INTERFACE_LIBS):")
    for name in interfaces:
        print(f"    {name}")
    print()
    print(
        f"# {len(mapped)} mapped, {len(candidates)} unmapped, {len(stale)} stale.",
        file=sys.stderr,
    )
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
