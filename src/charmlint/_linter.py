"""Core linter engine — loads charm context, discovers rules, runs them."""

import contextlib
import dataclasses
import pathlib
import re
from typing import Any

import yaml

from . import _config, _rules
from . import _models as models

# Use the libyaml-backed C loader when available — it's ~10× faster than
# the pure-Python SafeLoader and matches what ops does internally.
_SafeLoader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)

# Rule IDs follow ``<UPPERCASE LETTERS><DIGITS>`` (e.g. ``COS001``,
# ``TEST003``). The category prefix is the leading letter run.
_RULE_ID_PATTERN = re.compile(r"^([A-Z]+)([0-9]+)$")


def _category_of(rule_id: str) -> str:
    """Return the category prefix for a rule ID.

    Falls back to *rule_id* itself when the ID does not match the
    ``<LETTERS><DIGITS>`` convention so an unrecognised ID never
    accidentally matches a category in ``select`` / ``ignore``.
    """
    match = _RULE_ID_PATTERN.match(rule_id)
    if match is None:
        return rule_id
    return match.group(1)


class _YamlParseError(Exception):
    """Raised when a YAML file exists but cannot be parsed.

    Distinct from the absent-file case so the linter can tell the user
    which file is broken instead of falsely claiming the manifest is
    missing. Carries the original ``yaml.YAMLError`` message so the
    diagnostic surfaces the parser's line/column hint.
    """

    def __init__(self, path: pathlib.Path, reason: str) -> None:
        super().__init__(f"{path.name}: {reason}")
        self.path = path
        self.reason = reason


def _load_yaml(path: pathlib.Path) -> dict[str, Any]:
    """Load a YAML file, returning an empty dict on failure.

    Raises :class:`_YamlParseError` when *path* exists but the parser
    rejects it — a malformed manifest is fundamentally different from
    a missing one, and silently coercing to ``{}`` would have us
    report ``FATAL: No charmcraft.yaml or metadata.yaml found`` for a
    file that is right there but has a typo. ``OSError`` still maps
    to an empty dict because an unreadable file is closer to "not
    there" than to "broken syntax".
    """
    if not path.exists():
        return {}
    try:
        with path.open() as f:
            data = yaml.load(f, Loader=_SafeLoader)
    except yaml.YAMLError as exc:
        raise _YamlParseError(path, str(exc)) from exc
    except OSError:
        return {}
    return data if isinstance(data, dict) else {}


def _collect_python_files(charm_dir: pathlib.Path) -> list[pathlib.Path]:
    """Collect all Python files in src/ and lib/ directories."""
    files: list[pathlib.Path] = []
    for subdir in ("src", "lib"):
        d = charm_dir / subdir
        if d.is_dir():
            files.extend(sorted(d.rglob("*.py")))
    return files


def _read_python_sources(python_files: list[pathlib.Path]) -> dict[pathlib.Path, str]:
    """Read all Python files into a content cache.

    Eager loading is fine: a sweep over 379 real charms in the Hyrum cache showed
    a median footprint of 19 KB (3 files) and a worst case of 1.4 MB (40 files,
    canonical/kafka-k8s-operator) for the resident string values. p90 is 680 KB,
    p99 is 1.05 MB. Most rules iterate every file, so lazy loading wouldn't cut
    peak memory — it would just defer the same reads and add cache plumbing.
    """
    sources: dict[pathlib.Path, str] = {}
    for path in python_files:
        with contextlib.suppress(OSError):
            sources[path] = path.read_text(errors="replace")
    return sources


def _check_tests(charm_dir: pathlib.Path) -> tuple[bool, bool]:
    """Return (has_unit_tests, has_integration_tests)."""
    unit_dir = charm_dir / "tests" / "unit"
    integration_dir = charm_dir / "tests" / "integration"
    has_unit = unit_dir.is_dir() and bool(list(unit_dir.glob("test_*.py")))
    has_integration = integration_dir.is_dir() and bool(list(integration_dir.glob("test_*.py")))
    return has_unit, has_integration


def build_context(charm_dir: pathlib.Path) -> models.CharmContext:
    """Load all charm data into a CharmContext for rule evaluation."""
    charm_dir = charm_dir.resolve()

    # Load metadata from charmcraft.yaml or legacy metadata.yaml.
    # When both files exist, merge them: charmcraft.yaml takes precedence
    # for duplicate keys, but fields only in metadata.yaml are included.
    # This matches charmcraft's own behaviour for split-metadata charms.
    metadata = _load_yaml(charm_dir / "charmcraft.yaml")
    metadata_source = "charmcraft.yaml"
    metadata_fallback = _load_yaml(charm_dir / "metadata.yaml")
    if not metadata:
        metadata = metadata_fallback
        metadata_source = "metadata.yaml"
    elif metadata_fallback:
        for key in metadata_fallback:
            if key not in metadata:
                metadata[key] = metadata_fallback[key]

    # Load actions (charmcraft.yaml or actions.yaml).
    actions: dict[str, Any] = metadata.get("actions", {})
    if not actions:
        actions_data = _load_yaml(charm_dir / "actions.yaml")
        actions = actions_data if isinstance(actions_data, dict) else {}

    # Load config options (charmcraft.yaml or config.yaml).
    config_section = metadata.get("config", {})
    if isinstance(config_section, dict) and config_section.get("options"):
        config_options = config_section["options"]
    elif isinstance(config_section, dict) and config_section:
        config_options = config_section
    else:
        config_data = _load_yaml(charm_dir / "config.yaml")
        config_options = config_data.get("options", config_data) if config_data else {}

    # Collect Python files and read their contents.
    python_files = _collect_python_files(charm_dir)
    python_sources = _read_python_sources(python_files)

    # Read README.
    readme_content = ""
    readme_path = charm_dir / "README.md"
    if readme_path.exists():
        with contextlib.suppress(OSError):
            readme_content = readme_path.read_text(errors="replace")

    has_unit, has_integration = _check_tests(charm_dir)

    return models.CharmContext(
        charm_dir=charm_dir,
        metadata_source=metadata_source,
        metadata=metadata,
        actions=actions,
        config_options=config_options,
        python_files=python_files,
        python_sources=python_sources,
        readme_content=readme_content,
        has_tests_unit=has_unit,
        has_tests_integration=has_integration,
    )


def _should_run_rule(rule: _rules.Rule, config: _config.LintConfig) -> bool:
    """Determine whether a rule should run given the config."""
    rule_id = rule.id
    category = _category_of(rule_id)

    # Disable via severity override. A rule-level entry takes precedence
    # over a category-level one, so e.g. ``META = "off"`` plus
    # ``META001 = "error"`` keeps META001 running.
    rule_override = config.severity_overrides.get(rule_id)
    if rule_override == "off":
        return False
    if rule_override is None and config.severity_overrides.get(category) == "off":
        return False

    # If select is set, only run rules named by ID or category.
    if config.select and category not in config.select and rule_id not in config.select:
        return False

    # If ignore contains this specific rule or category, skip it.
    return not (rule_id in config.ignore or category in config.ignore)


def _effective_severity(rule: _rules.Rule, config: _config.LintConfig) -> models.Severity | None:
    """Resolve the effective severity for a rule, applying config overrides.

    Rule-level overrides take precedence over category-level ones,
    mirroring :func:`_should_run_rule`.
    """
    rule_id = rule.id
    override = config.severity_overrides.get(rule_id) or config.severity_overrides.get(
        _category_of(rule_id)
    )
    if override and override != "off":
        try:
            return models.Severity(override)
        except ValueError:
            pass
    return None


def lint(
    charm_dir: pathlib.Path,
    config: _config.LintConfig | None = None,
) -> models.LintReport:
    """Run all enabled rules against a charm directory.

    This is the main public API.
    """
    if config is None:
        config = _config.LintConfig()

    try:
        context = build_context(charm_dir)
    except _YamlParseError as exc:
        return models.LintReport(
            charm_dir=charm_dir,
            diagnostics=[
                models.Diagnostic(
                    rule_id="FATAL",
                    severity=models.Severity.ERROR,
                    message=f"Could not parse {exc.path.name}: {exc.reason}",
                    path=str(exc.path.relative_to(charm_dir))
                    if exc.path.is_relative_to(charm_dir)
                    else str(exc.path),
                )
            ],
        )

    if not context.metadata:
        return models.LintReport(
            charm_dir=charm_dir,
            diagnostics=[
                models.Diagnostic(
                    rule_id="FATAL",
                    severity=models.Severity.ERROR,
                    message=(
                        "No charmcraft.yaml or metadata.yaml found — is this a charm directory?"
                    ),
                )
            ],
        )

    all_diagnostics: list[models.Diagnostic] = []

    for rule in _rules.get_all_rules().values():
        if not _should_run_rule(rule, config):
            continue

        diagnostics = rule.check(context)

        # Apply severity overrides.
        override = _effective_severity(rule, config)
        if override is not None:
            diagnostics = [dataclasses.replace(d, severity=override) for d in diagnostics]

        all_diagnostics.extend(diagnostics)

    # Filter by minimum severity.
    if config.min_severity is not None:
        max_rank = config.min_severity.rank
        all_diagnostics = [d for d in all_diagnostics if d.severity.rank <= max_rank]

    # Sort by location rather than rule-registration order so output is
    # stable and diff-friendly as rules are added. Diagnostics without a
    # path (charm-level findings) sort first.
    all_diagnostics.sort(key=lambda d: (d.path or "", d.line or 0, d.rule_id))

    return models.LintReport(charm_dir=charm_dir, diagnostics=all_diagnostics)
