"""Configuration loader for charmlint.

Reads ``.charmlint.yaml`` from the charm directory (or a path specified
via CLI) and merges with defaults.  Configuration supports:

- ``rules``: per-rule severity overrides (e.g. ``COS005: error``,
  ``STR002: off``)
- ``select``: list of category prefixes to enable (e.g. ``[COS, META]``)
- ``ignore``: list of rule IDs or category prefixes to skip
"""

import contextlib
import dataclasses
import pathlib
from typing import Any

import yaml

from . import models

_CONFIG_FILENAME = ".charmlint.yaml"


@dataclasses.dataclass
class LintConfig:
    """Resolved lint configuration."""

    severity_overrides: dict[str, str] = dataclasses.field(default_factory=dict)
    select: list[str] = dataclasses.field(default_factory=list)
    ignore: list[str] = dataclasses.field(default_factory=list)
    min_severity: models.Severity | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LintConfig":
        """Build a LintConfig from a parsed YAML dict."""
        rules = data.get("rules", {})
        severity_overrides: dict[str, str] = {}
        if isinstance(rules, dict):
            for key, value in rules.items():
                severity_overrides[str(key)] = str(value).lower()

        select_raw = data.get("select", [])
        select = [str(s) for s in select_raw] if isinstance(select_raw, list) else []

        ignore_raw = data.get("ignore", [])
        ignore = [str(s) for s in ignore_raw] if isinstance(ignore_raw, list) else []

        min_sev_raw = data.get("severity")
        min_severity = None
        if min_sev_raw:
            with contextlib.suppress(ValueError):
                min_severity = models.Severity(str(min_sev_raw).lower())

        return cls(
            severity_overrides=severity_overrides,
            select=select,
            ignore=ignore,
            min_severity=min_severity,
        )


def load_config(charm_dir: pathlib.Path, config_path: pathlib.Path | None = None) -> LintConfig:
    """Load configuration from a ``.charmlint.yaml`` file.

    Searches the charm directory for a config file.  If *config_path*
    is given, that file is used instead.  Returns an empty config if
    no file is found.
    """
    path = config_path or (charm_dir / _CONFIG_FILENAME)
    if not path.exists():
        return LintConfig()

    try:
        with path.open() as f:
            data = yaml.safe_load(f)
    except (yaml.YAMLError, OSError):
        return LintConfig()

    if not isinstance(data, dict):
        return LintConfig()

    return LintConfig.from_dict(data)
