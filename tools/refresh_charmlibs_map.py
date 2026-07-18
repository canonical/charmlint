"""Print the current ``charmlibs-*`` PyPI namespace as a maintenance aid.

Run this before releasing a new charmlint version to see whether new
``charmlibs-*`` packages have shown up on PyPI that LIBRARY-001 doesn't
yet map. Any new operator_libs_linux submodules go straight into
``_OP_LIBS_LINUX_SUBMODULES``; new interface libs go into
``_INTERFACE_PREFIXES`` after confirming the source-charm name in
Charmhub (which is what the fetch-libs import path uses).

Usage:
    python tools/refresh_charmlibs_map.py

Deliberately kept off the runtime path — LIBRARY-001 must stay offline.
"""

from __future__ import annotations

import re
import sys
import urllib.request

_SIMPLE_INDEX = "https://pypi.org/simple/"
_PACKAGE_RE = re.compile(r">(charmlibs[a-z0-9-]*)</a>")


def fetch_charmlibs() -> list[str]:
    with urllib.request.urlopen(_SIMPLE_INDEX, timeout=30) as response:
        body = response.read().decode("utf-8", errors="replace")
    return sorted({m.group(1) for m in _PACKAGE_RE.finditer(body)})


def main() -> int:
    packages = fetch_charmlibs()
    if not packages:
        print("no charmlibs-* packages found on PyPI", file=sys.stderr)
        return 1

    top_level = sorted(
        p for p in packages if p != "charmlibs" and not p.startswith("charmlibs-interfaces")
    )
    interfaces = sorted(p for p in packages if p.startswith("charmlibs-interfaces-"))

    print("# All charmlibs-* packages currently on PyPI. Cross-check against")
    print("# _OP_LIBS_LINUX_SUBMODULES and _INTERFACE_PREFIXES in _rules/libraries.py.")
    print("# The fetch-libs prefix isn't derivable from the PyPI name for interface libs —")
    print("# look up the owning charm on charmhub before adding a mapping.")
    print()
    print("# Top-level charmlibs (candidates for _OP_LIBS_LINUX_SUBMODULES if named after")
    print("# an operator_libs_linux submodule; otherwise informational only):")
    for name in top_level:
        print(f"    {name}")
    print()
    print("# charmlibs-interfaces-*:")
    for name in interfaces:
        print(f"    {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
