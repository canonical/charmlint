"""charmlint — a deterministic linter for Juju charms.

Use the ``charmlint`` CLI. This package has no stable Python API.
"""


def __getattr__(name: str) -> str:
    """Resolve ``__version__`` on first access.

    ``importlib.metadata`` costs around 20ms to import, which is a large
    fraction of the CLI's startup, and nothing but ``--version`` needs it.
    """
    if name != "__version__":
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib.metadata

    try:
        return importlib.metadata.version("charmlint")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0+unknown"
