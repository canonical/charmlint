"""Core linter engine — loads charm context, discovers rules, runs them."""

import contextlib
import pathlib
import re
from typing import Any

import yaml

from . import _config, _rules
from . import _models as models

# Use the libyaml-backed C loader when available — it's ~10× faster than
# the pure-Python SafeLoader and matches what ops does internally.
_SafeLoader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)

# Rule IDs follow ``<UPPERCASE-CATEGORY>-<DIGITS>`` (e.g.
# ``METADATA-001``, ``SECURITY-003``). The category is everything before
# the final dash-and-digits.
_RULE_ID_PATTERN = re.compile(r"^([A-Z]+)-([0-9]+)$")


def _category_of(rule_id: str) -> str:
    """Return the category prefix for a rule ID.

    Falls back to *rule_id* itself when the ID does not match the
    ``<CATEGORY>-<DIGITS>`` convention so an unrecognised ID never
    accidentally matches a category in ``select`` / ``ignore``.
    """
    match = _RULE_ID_PATTERN.match(rule_id)
    if match is None:
        return rule_id
    return match.group(1)


class _FileLoadError(Exception):
    """Raised when a required file exists but cannot be loaded.

    Covers YAML syntax errors, OS-level read failures, and any other
    failure to turn a present file into usable data. Distinct from the
    absent-file case so the linter can tell the user which file is
    broken instead of falsely claiming the manifest is missing.
    """

    def __init__(self, path: pathlib.Path, reason: str) -> None:
        super().__init__(f"{path.name}: {reason}")
        self.path = path
        self.reason = reason


def _load_yaml(path: pathlib.Path) -> dict[str, Any]:
    """Load a YAML file.

    Returns an empty dict only when *path* does not exist. Every other
    failure (unreadable file, YAML syntax error, top-level value that
    isn't a mapping) is surfaced via :class:`_FileLoadError` — a file
    that is there but broken should never be silently reported as
    missing.
    """
    if not path.exists():
        return {}
    try:
        with path.open() as f:
            data = yaml.load(f, Loader=_SafeLoader)
    except yaml.YAMLError as exc:
        raise _FileLoadError(path, str(exc)) from exc
    except OSError as exc:
        raise _FileLoadError(path, f"could not read: {exc}") from exc
    if not isinstance(data, dict):
        raise _FileLoadError(path, "top-level YAML value is not a mapping")
    return data


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
        try:
            sources[path] = path.read_text(errors="replace")
        except OSError as exc:
            raise _FileLoadError(path, f"could not read: {exc}") from exc
    return sources


def _check_tests(charm_dir: pathlib.Path) -> tuple[bool, bool]:
    """Return (has_unit_tests, has_integration_tests).

    Accepts ``tests/unit/`` and the reactive-charm ``unit_tests/`` layout
    for unit tests, and matches ``test_*.py`` at any depth so nested
    suites (e.g. ``tests/unit/test_charm/test_charm.py``) count.
    """
    unit_roots = [charm_dir / "tests" / "unit", charm_dir / "unit_tests"]
    has_unit = any(d.is_dir() and next(d.rglob("test_*.py"), None) is not None for d in unit_roots)
    integration_dir = charm_dir / "tests" / "integration"
    has_integration = (
        integration_dir.is_dir() and next(integration_dir.rglob("test_*.py"), None) is not None
    )
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
    """Determine whether a rule should run given the config.

    Precedence: more-specific directives win over less-specific ones.
    A rule ID beats a category, so ``select=["FOO001"]`` runs even when
    ``ignore=["FOO"]`` — the user was more specific about running FOO001
    than about ignoring FOO.
    """
    rule_id = rule.id
    category = rule.category

    if rule_id in config.ignore:
        return False
    if rule_id in config.select:
        return True
    if category in config.ignore:
        return False
    if config.select:
        return category in config.select
    return True


def _effective_severity(rule: _rules.Rule, config: _config.LintConfig) -> models.Severity | None:
    """Resolve the effective severity for a rule, applying config overrides."""
    rule_id = rule.id
    override = config.severity_overrides.get(rule_id)
    if override:
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
    except _FileLoadError as exc:
        return models.LintReport.from_diagnostics(
            charm_dir=charm_dir,
            diagnostics=[
                models.Diagnostic(
                    rule_id="FATAL",
                    severity=models.Severity.ERROR,
                    message=f"Could not load {exc.path.name}: {exc.reason}",
                    path=str(exc.path.relative_to(charm_dir))
                    if exc.path.is_relative_to(charm_dir)
                    else str(exc.path),
                )
            ],
        )

    if not context.metadata:
        return models.LintReport.from_diagnostics(
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
            diagnostics = [
                models.Diagnostic(
                    rule_id=d.rule_id,
                    severity=override,
                    message=d.message,
                    path=d.path,
                    line=d.line,
                    fix_hint=d.fix_hint,
                )
                for d in diagnostics
            ]

        # Filter by minimum severity.
        if config.min_severity:
            severity_order = {
                models.Severity.ERROR: 0,
                models.Severity.WARNING: 1,
                models.Severity.INFO: 2,
            }
            min_order = severity_order.get(config.min_severity, 2)
            diagnostics = [
                d for d in diagnostics if severity_order.get(d.severity, 2) <= min_order
            ]

        all_diagnostics.extend(diagnostics)

    return models.LintReport.from_diagnostics(charm_dir=charm_dir, diagnostics=all_diagnostics)
