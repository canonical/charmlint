"""Core linter engine — loads charm context, discovers rules, runs them."""

import contextlib
import dataclasses
import pathlib
import re

from . import _ast, _config, _discovery, _noqa, _rules, _yaml
from . import _models as models

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


def _collect_python_files(charm_dir: pathlib.Path) -> list[pathlib.Path]:
    """Collect all Python files in the charm's source and test trees.

    Covers ``src/``, ``lib/`` and ``tests/``. Each file is tagged with a
    :class:`models.Scope` when parsed, and a rule selects the scope it
    means, so collecting a tree here does not put it in front of a rule
    that did not ask for it.
    """
    files: list[pathlib.Path] = []
    for subdir in ("src", "lib", "tests"):
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
            raise _yaml.FileLoadError(path, f"could not read: {exc}") from exc
    return sources


def _parse_python_modules(
    sources: dict[pathlib.Path, str], charm_dir: pathlib.Path, charm_name: str | None
) -> list[models.Module]:
    """Parse every collected source once, for all rules to share.

    A source that does not parse is a :class:`_yaml.FileLoadError`, the same as a
    malformed YAML file. charmlint does not duplicate what ruff and a type
    checker already report, and both run before it; a charm that reaches
    charmlint with a broken ``src/charm.py`` should be told so rather than
    handed a report that looks clean.
    """
    modules: list[models.Module] = []
    for path, text in sources.items():
        try:
            modules.append(_ast.parse(path, text, charm_dir, charm_name))
        except SyntaxError as exc:
            line = f" (line {exc.lineno})" if exc.lineno else ""
            raise _yaml.FileLoadError(path, f"could not parse{line}: {exc.msg}") from exc
    return modules


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
    # Every key keeps the file it was read from, so rules that care which
    # file a key came from (the two files accept different keys) can tell
    # them apart, and diagnostics anchor to the right one.
    charmcraft = _yaml.load(charm_dir / "charmcraft.yaml")
    legacy = _yaml.load(charm_dir / "metadata.yaml")
    metadata = _yaml.merge(charmcraft, legacy) if charmcraft else legacy

    # Load actions (charmcraft.yaml or actions.yaml).
    actions = metadata.get("actions")
    if not actions:
        actions = _yaml.load(charm_dir / "actions.yaml")
    actions = _mapping_or_absent(actions)

    # Load config options (charmcraft.yaml or config.yaml).
    config_section = metadata.get("config")
    if "options" in config_section:
        # `config: {options: }` is an empty (not absent) option set — take
        # it as-is, rather than falling through and treating the literal
        # key 'options' as an option name.
        config_options = config_section["options"]
    elif config_section:
        config_options = config_section
    else:
        config_data = _yaml.load(charm_dir / "config.yaml")
        config_options = config_data.get("options") if "options" in config_data else config_data
    config_options = _mapping_or_absent(config_options)

    # Collect Python files and read their contents.
    python_files = _collect_python_files(charm_dir)
    python_sources = _read_python_sources(python_files)
    name = metadata.get("name").value
    python_modules = _parse_python_modules(
        python_sources, charm_dir, name if isinstance(name, str) else None
    )

    # Read README.
    readme_content = ""
    readme_path = charm_dir / "README.md"
    if readme_path.exists():
        with contextlib.suppress(OSError):
            readme_content = readme_path.read_text(errors="replace")

    has_unit, has_integration = _check_tests(charm_dir)

    return models.CharmContext(
        charm_dir=charm_dir,
        metadata=metadata,
        actions=actions,
        config_options=config_options,
        python_files=python_files,
        python_sources=python_sources,
        python_modules=python_modules,
        readme_content=readme_content,
        has_tests_unit=has_unit,
        has_tests_integration=has_integration,
    )


def _mapping_or_absent(node: models.Yaml) -> models.Yaml:
    """Return *node* if it holds a mapping, else an absent node for its file.

    A section written as something other than a mapping (``actions: []``)
    has no entries to check, and reducing it here keeps every rule from
    repeating the same shape guard.
    """
    if isinstance(node.value, dict):
        return node
    return models.Yaml.absent(node.source)


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


def _lint_charm(charm_dir: pathlib.Path, config: _config.LintConfig) -> list[models.Diagnostic]:
    """Run the enabled rules against one charm, and apply its ``noqa`` directives.

    Diagnostic paths are relative to *charm_dir*, as a rule reports them.
    """
    try:
        context = build_context(charm_dir)
    except _yaml.FileLoadError as exc:
        return [
            models.Diagnostic(
                rule_id="FATAL",
                severity=models.Severity.ERROR,
                message=f"Could not load {exc.path.name}: {exc.reason}",
                path=str(exc.path.relative_to(charm_dir))
                if exc.path.is_relative_to(charm_dir)
                else str(exc.path),
            )
        ]

    if not context.metadata:
        return [
            models.Diagnostic(
                rule_id="FATAL",
                severity=models.Severity.ERROR,
                message="No charmcraft.yaml or metadata.yaml found — is this a charm directory?",
            )
        ]

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

    return _apply_noqa(charm_dir, all_diagnostics)


def _prefixed(diagnostic: models.Diagnostic, prefix: pathlib.PurePosixPath) -> models.Diagnostic:
    """Return *diagnostic* with its path moved from charm-relative to root-relative.

    Only reached when one run covers several charms, where a bare
    ``src/charm.py`` would not say which charm it came from.
    """
    if diagnostic.path is None:
        return diagnostic
    return dataclasses.replace(diagnostic, path=str(prefix / diagnostic.path))


def lint(
    path: pathlib.Path,
    config: _config.LintConfig | None = None,
) -> models.LintReport:
    """Run all enabled rules against a charm directory.

    This is the main public API.

    *path* is normally a single charm. It may also be a repository holding
    several charms, in which case every charm below it is linted and the
    findings are gathered into one report, with each diagnostic's path
    written relative to *path* so it names the charm it belongs to.
    """
    if config is None:
        config = _config.LintConfig()

    path = path.resolve()
    charm_dirs = _discovery.discover_charms(path)

    if not charm_dirs:
        return models.LintReport.from_diagnostics(
            charm_dir=path,
            diagnostics=[
                models.Diagnostic(
                    rule_id="FATAL",
                    severity=models.Severity.ERROR,
                    message=(
                        "No charmcraft.yaml or metadata.yaml found here or in any "
                        "directory below — is this a charm directory?"
                    ),
                )
            ],
        )

    if charm_dirs == [path]:
        return models.LintReport.from_diagnostics(
            charm_dir=path, diagnostics=_lint_charm(path, config)
        )

    diagnostics: list[models.Diagnostic] = []
    for charm_dir in charm_dirs:
        prefix = pathlib.PurePosixPath(charm_dir.relative_to(path))
        diagnostics.extend(_prefixed(d, prefix) for d in _lint_charm(charm_dir, config))
    return models.LintReport.from_diagnostics(charm_dir=path, diagnostics=diagnostics)


# YAML files are the only ones scanned for ``noqa`` directives.
_NOQA_SUFFIXES = frozenset({".yaml", ".yml"})


def _apply_noqa(
    charm_dir: pathlib.Path, diagnostics: list[models.Diagnostic]
) -> list[models.Diagnostic]:
    """Drop diagnostics silenced by a ``noqa`` directive in their file.

    Only YAML files are scanned. A diagnostic with no path, or one in a
    non-YAML or unreadable file, is always kept.
    """
    cache: dict[str, _noqa.FileNoqa | None] = {}

    def noqa_for(rel_path: str) -> _noqa.FileNoqa | None:
        if rel_path not in cache:
            file = charm_dir / rel_path
            if file.suffix.lower() not in _NOQA_SUFFIXES:
                cache[rel_path] = None
            else:
                try:
                    cache[rel_path] = _noqa.parse(file.read_text(errors="replace"))
                except OSError:
                    cache[rel_path] = None
        return cache[rel_path]

    kept: list[models.Diagnostic] = []
    for d in diagnostics:
        if d.path is None:
            kept.append(d)
            continue
        file_noqa = noqa_for(d.path)
        if file_noqa is not None and file_noqa.suppresses(d.rule_id, d.line):
            continue
        kept.append(d)
    return kept
