"""Allow running charmlint as ``python -m charmlint``."""

from . import _cli

if __name__ == "__main__":
    _cli.cli_entry()
