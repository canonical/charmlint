"""Configuration loader for charmlint.

Configuration is read from ``pyproject.toml`` (``[tool.charmlint]``),
``charmlint.toml``, or ``.charmlint.toml`` — discovered by walking up
from the charm directory, in the manner of ruff. A path passed via
``--config`` short-circuits discovery.

Keys under ``[tool.charmlint]``:

- ``severity``: minimum severity to report (``error``, ``warning``, ``info``)
- ``select`` / ``extend-select``: rules to enable
- ``ignore`` / ``extend-ignore``: rules to skip
- ``per-rule-severity``: per-rule severity overrides (e.g.
  ``"SECURITY-001" = "error"``)

Everywhere a rule is named — ``select``, ``ignore``, and the keys of
``per-rule-severity`` — it may be spelled as a rule ID
(``SECURITY-001``), a rule name (``secret-in-plain-config``) or a
category (``SECURITY``). A spelling that names nothing is rejected
rather than silently ignored, so a typo is not mistaken for a rule that
never fires.
"""

import contextlib
import dataclasses
import pathlib
import sys
import tomllib
from typing import Any

from . import _models as models
from . import _selectors

_PYPROJECT = "pyproject.toml"
STANDALONE_NAMES = ("charmlint.toml", ".charmlint.toml")


class ConfigError(Exception):
    """Raised when a config file exists but cannot be used."""

    def __init__(self, path: pathlib.Path, reason: str) -> None:
        super().__init__(f"{path}: {reason}")
        self.path = path
        self.reason = reason


@dataclasses.dataclass
class LintConfig:
    """Resolved lint configuration."""

    severity_overrides: dict[str, str] = dataclasses.field(default_factory=dict)
    select: list[str] = dataclasses.field(default_factory=list)
    ignore: list[str] = dataclasses.field(default_factory=list)
    min_severity: models.Severity | None = None
    source_path: pathlib.Path | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LintConfig":
        """Build a LintConfig from a parsed ``[tool.charmlint]`` table."""
        severity_overrides: dict[str, str] = {}
        rules = data.get("per-rule-severity", {})
        if isinstance(rules, dict):
            for key, value in rules.items():
                severity_overrides[str(key)] = str(value).lower()

        select = _str_list(data.get("select")) + _str_list(data.get("extend-select"))
        ignore = _str_list(data.get("ignore")) + _str_list(data.get("extend-ignore"))

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


def _validate(config: "LintConfig", path: pathlib.Path) -> None:
    """Reject configs that name nothing, or that contradict themselves."""
    unknown = sorted(
        {
            token
            for token in (*config.select, *config.ignore, *config.severity_overrides)
            if not _selectors.resolve(token)
        }
    )
    if unknown:
        raise ConfigError(
            path,
            f"not a known rule ID, rule name or category: {', '.join(unknown)}",
        )

    # Only tokens of the same specificity can contradict each other: a
    # rule named in ``select`` and its category named in ``ignore`` is
    # the ordinary way to run one rule out of a category.
    for covered in (_rules_covered, _categories_covered):
        overlap = sorted(covered(config.select) & covered(config.ignore))
        if overlap:
            raise ConfigError(path, f"select and ignore both cover: {', '.join(overlap)}")


def _rules_covered(tokens: list[str]) -> set[str]:
    """The rule IDs named specifically — by ID or name — among *tokens*."""
    return {
        rule_id
        for token in tokens
        if not _selectors.is_category(token)
        for rule_id in _selectors.resolve(token)
    }


def _categories_covered(tokens: list[str]) -> set[str]:
    """The rule IDs named by the category tokens among *tokens*."""
    return {
        rule_id
        for token in tokens
        if _selectors.is_category(token)
        for rule_id in _selectors.resolve(token)
    }


def _read_toml(path: pathlib.Path) -> dict[str, Any] | None:
    """Parse a TOML file.

    Returns ``None`` if the file cannot be opened. Raises
    :class:`ConfigError` if the file exists but is malformed TOML or has
    a non-table top-level value — silently walking past a broken config
    would mask real user errors.
    """
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except OSError:
        return None
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(path, str(exc)) from exc
    if not isinstance(data, dict):
        raise ConfigError(path, "top-level TOML value is not a table")
    return data


def _extract(
    data: dict[str, Any], path: pathlib.Path, *, from_pyproject: bool
) -> dict[str, Any] | None:
    """Pull the charmlint table out of a parsed TOML document.

    Returns ``None`` if a ``pyproject.toml`` has no ``[tool.charmlint]``
    section, so discovery keeps walking. Raises :class:`ConfigError` if
    the section is present but not a table.
    """
    if from_pyproject:
        tool = data.get("tool")
        if not isinstance(tool, dict):
            return None
        if "charmlint" not in tool:
            return None
        section = tool["charmlint"]
        if not isinstance(section, dict):
            raise ConfigError(path, "[tool.charmlint] is not a table")
        return section
    return data


def _discover(start: pathlib.Path) -> tuple[pathlib.Path, dict[str, Any]] | None:
    """Walk up from *start* looking for a config file.

    A malformed ``charmlint.toml`` or ``.charmlint.toml`` propagates the
    :class:`ConfigError` — the user pointed at that file, so we should
    not silently ignore it. A malformed ``pyproject.toml`` in an
    ancestor directory prints a warning to stderr and keeps walking:
    it may not belong to this project at all.
    """
    for directory in (start, *start.parents):
        for name in STANDALONE_NAMES:
            candidate = directory / name
            if candidate.is_file():
                data = _read_toml(candidate)
                if data is not None:
                    return candidate, data
        pyproject = directory / _PYPROJECT
        if pyproject.is_file():
            try:
                data = _read_toml(pyproject)
                if data is None:
                    continue
                section = _extract(data, pyproject, from_pyproject=True)
            except ConfigError as exc:
                print(f"Warning: {exc}", file=sys.stderr)
                continue
            if section is not None:
                return pyproject, section
    return None


def load_config(charm_dir: pathlib.Path, config_path: pathlib.Path | None = None) -> LintConfig:
    """Load configuration, searching upward from *charm_dir*.

    If *config_path* is provided it is used directly: a ``pyproject.toml``
    has its ``[tool.charmlint]`` table extracted; any other filename is
    treated as a standalone charmlint TOML file. Returns an empty config
    if nothing is found.
    """
    if config_path is not None:
        data = _read_toml(config_path)
        if data is None:
            raise ConfigError(config_path, "file not found or unreadable")
        section = _extract(data, config_path, from_pyproject=config_path.name == _PYPROJECT)
        if section is None:
            return LintConfig()
        config = LintConfig.from_dict(section)
        config.source_path = config_path
        _validate(config, config_path)
        return config

    found = _discover(charm_dir)
    if found is None:
        return LintConfig()
    path, data = found
    config = LintConfig.from_dict(data)
    config.source_path = path
    _validate(config, path)
    return config
