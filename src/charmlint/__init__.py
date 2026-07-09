"""charmlint — a deterministic linter for Juju charms.

Use the ``charmlint`` CLI. This package has no stable Python API.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("charmlint")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"
