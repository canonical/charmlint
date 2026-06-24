"""Configuration loader for charmlint.

Configuration is read from ``pyproject.toml`` (``[tool.charmlint]``),
``charmlint.toml``, or ``.charmlint.toml`` — discovered by walking up
from the charm directory, in the manner of ruff. A path passed via
``--config`` short-circuits discovery.

Top-level keys:

- ``severity``: minimum severity to report (``error``, ``warning``, ``info``)

Lint selection lives under ``[tool.charmlint.lint]`` (mirroring ruff):

- ``select`` / ``extend-select``: category prefixes or rule IDs to enable
- ``ignore`` / ``extend-ignore``: category prefixes or rule IDs to skip
- ``per-rule-severity``: per-rule severity overrides (e.g.
  ``COS005 = "error"``, ``STR002 = "off"``) — charmlint-specific, no
  direct ruff analogue
"""

import contextlib
import dataclasses
import pathlib
import tomllib
from typing import Any

from . import _models as models

_PYPROJECT = "pyproject.toml"
_STANDALONE_NAMES = ("charmlint.toml", ".charmlint.toml")


@dataclasses.dataclass
class LintConfig:
    """Resolved lint configuration."""

    severity_overrides: dict[str, str] = dataclasses.field(default_factory=dict)
    select: list[str] = dataclasses.field(default_factory=list)
    ignore: list[str] = dataclasses.field(default_factory=list)
    min_severity: models.Severity | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LintConfig":
        """Build a LintConfig from a parsed ``[tool.charmlint]`` table."""
        lint = data.get("lint", {})
        if not isinstance(lint, dict):
            lint = {}

        severity_overrides: dict[str, str] = {}
        rules = lint.get("per-rule-severity", {})
        if isinstance(rules, dict):
            for key, value in rules.items():
                severity_overrides[str(key)] = str(value).lower()

        select = _str_list(lint.get("select")) + _str_list(lint.get("extend-select"))
        ignore = _str_list(lint.get("ignore")) + _str_list(lint.get("extend-ignore"))

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


def _str_list(value: Any) -> list[str]:
    """Coerce a TOML list value to ``list[str]``, ignoring non-lists."""
    if not isinstance(value, list):
        return []
    return [str(s) for s in value]


def _read_toml(path: pathlib.Path) -> dict[str, Any] | None:
    """Parse a TOML file, returning ``None`` on any error."""
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _extract(data: dict[str, Any], from_pyproject: bool) -> dict[str, Any] | None:
    """Pull the charmlint table out of a parsed TOML document.

    Returns ``None`` if a ``pyproject.toml`` has no ``[tool.charmlint]``
    section, so discovery keeps walking.
    """
    if from_pyproject:
        tool = data.get("tool")
        if not isinstance(tool, dict):
            return None
        section = tool.get("charmlint")
        return section if isinstance(section, dict) else None
    return data


def _discover(start: pathlib.Path) -> tuple[pathlib.Path, dict[str, Any]] | None:
    """Walk up from *start* looking for a config file."""
    for directory in (start, *start.parents):
        for name in _STANDALONE_NAMES:
            candidate = directory / name
            if candidate.is_file():
                data = _read_toml(candidate)
                if data is not None:
                    return candidate, data
        pyproject = directory / _PYPROJECT
        if pyproject.is_file():
            data = _read_toml(pyproject)
            if data is not None:
                section = _extract(data, from_pyproject=True)
                if section is not None:
                    return pyproject, section
    return None


def load_config(
    charm_dir: pathlib.Path, config_path: pathlib.Path | None = None
) -> LintConfig:
    """Load configuration, searching upward from *charm_dir*.

    If *config_path* is provided it is used directly: a ``pyproject.toml``
    has its ``[tool.charmlint]`` table extracted; any other filename is
    treated as a standalone charmlint TOML file. Returns an empty config
    if nothing is found.
    """
    if config_path is not None:
        data = _read_toml(config_path)
        if data is None:
            return LintConfig()
        section = _extract(data, from_pyproject=config_path.name == _PYPROJECT)
        if section is None:
            return LintConfig()
        return LintConfig.from_dict(section)

    found = _discover(charm_dir)
    if found is None:
        return LintConfig()
    return LintConfig.from_dict(found[1])
