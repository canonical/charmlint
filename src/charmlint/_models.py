"""Core data models for charmlint."""

import ast
import contextlib
import dataclasses
import enum
import pathlib
from collections.abc import Iterable, Iterator
from typing import Any


@dataclasses.dataclass(frozen=True)
class Yaml:
    """A value read from one of a charm's YAML files, with its provenance.

    A charm's metadata is spread over up to four files
    (``charmcraft.yaml``, ``metadata.yaml``, ``actions.yaml``,
    ``config.yaml``), and a split-metadata charm can declare one
    top-level key in one file and the next key in another. A rule that
    reports a finding needs to know *which* file the value it is
    complaining about came from, and *which line* in that file, so the
    diagnostic points at the right place and ``# noqa`` on that line
    can silence it.

    Carrying that on the value itself means a rule writes::

        self.diagnostic(..., path=option.source, line=option.line)

    instead of consulting a side table of line numbers keyed by name,
    per section, that the linter core had to populate in advance.

    ``value`` is the plain Python value PyYAML would have constructed;
    ``source`` is the *file name* the value was read from (relative to
    the charm directory, e.g. ``"metadata.yaml"``); ``line`` is the
    1-based line of the key that introduced the value, or ``None`` for
    a value with no line of its own.

    Nested mappings are wrapped too, so ``.get()`` chains keep
    provenance::

        context.metadata.get("links").get("issues").source

    So are sequences, whose elements are reached through
    :attr:`elements` rather than through the mapping lookups: a list
    written one item per line gives each element its own line, so a
    finding about one URL in a list anchors to that URL::

        for element in node.elements or ():
            ...  # element.value, element.line

    The mapping lookups stay mapping-only on purpose. ``items()`` being
    empty for a sequence is what lets a rule treat a section written as
    a list as malformed and yield nothing, rather than reporting on
    list indices as though they were names.

    ``bool(node)`` is the truthiness of the underlying value, so a
    missing key, an explicit ``null``, and an empty string are all
    falsy — which is what "empty or missing" rules want. Use
    :attr:`present` when the distinction matters (an explicit
    ``default: ""`` is a default; an explicit
    ``additionalProperties: false`` is a choice).
    """

    value: Any = None
    source: str = ""
    line: int | None = None
    # False only for a node returned by ``get()`` for a key that is not
    # in the mapping. A key present with a ``null`` value is ``present``
    # with a ``value`` of ``None``.
    present: bool = True
    # Wrapped children, for a mapping node. Excluded from ``repr`` so
    # printing a node in a traceback doesn't dump the whole document.
    children: "dict[Any, Yaml] | None" = dataclasses.field(default=None, repr=False)
    # Wrapped elements, for a sequence node. Kept apart from ``children``
    # so the mapping lookups stay mapping-only; excluded from ``repr``
    # for the same reason.
    elements: "list[Yaml] | None" = dataclasses.field(default=None, repr=False)

    @classmethod
    def absent(cls, source: str) -> "Yaml":
        """Return a node standing for a value that is not there.

        It keeps *source* so a rule reporting the absence still names a
        file, but has no line: there is no key to point at.
        """
        return cls(value=None, source=source, line=None, present=False)

    def __bool__(self) -> bool:
        return bool(self.value)

    def __contains__(self, key: object) -> bool:
        return key in (self.children or {})

    def __iter__(self) -> "Iterator[Any]":
        """Iterate the keys of a mapping node (nothing, for a non-mapping)."""
        return iter(self.children or {})

    def __getitem__(self, key: object) -> "Yaml":
        return (self.children or {})[key]

    def get(self, key: object) -> "Yaml":
        """Return the child node for *key*, or an absent node.

        Never raises and always returns a ``Yaml``, so lookups chain
        through missing and non-mapping values alike.
        """
        child = (self.children or {}).get(key)
        if child is None:
            return Yaml.absent(self.source)
        return child

    def items(self) -> "Iterable[tuple[Any, Yaml]]":
        """Iterate ``(key, node)`` pairs of a mapping node.

        Empty for a non-mapping, which is what the rules want: a
        malformed section yields no findings rather than a crash, the
        same as the ``isinstance(..., dict)`` guards this replaces.

        Keys are whatever YAML constructed, which is not always a
        string — an unquoted ``on:`` key is the boolean ``True`` under
        YAML 1.1. Rules that put a key in a message must cope with that.
        """
        return (self.children or {}).items()


class Severity(enum.StrEnum):
    """Diagnostic severity level."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclasses.dataclass(frozen=True)
class Diagnostic:
    """A single lint finding."""

    rule_id: str
    severity: Severity
    message: str
    path: str | None = None
    line: int | None = None
    fix_hint: str | None = None
    reference_url: str | None = None

    def format_text(self, charm_dir: pathlib.Path | None = None) -> str:
        """Format as a ruff-style single-line diagnostic."""
        location = self.path or ""
        if charm_dir and self.path:
            with contextlib.suppress(ValueError):
                location = str(pathlib.Path(self.path).relative_to(charm_dir))
        if self.line is not None:
            location = f"{location}:{self.line}"
        prefix = f"{location}: " if location else ""
        return f"{prefix}{self.rule_id} {self.message}"

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-friendly dict."""
        result: dict[str, Any] = {
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "message": self.message,
        }
        if self.path is not None:
            result["path"] = self.path
        if self.line is not None:
            result["line"] = self.line
        if self.fix_hint is not None:
            result["fix_hint"] = self.fix_hint
        if self.reference_url is not None:
            result["reference_url"] = self.reference_url
        return result


class Scope(enum.StrEnum):
    """Which part of the charm tree a module lives in.

    Rules are almost always interested in exactly one of these. ``SRC`` is
    the charm's own code; ``LIB`` is vendored ``charmcraft fetch-lib``
    output, which the charm author does not maintain and should not be
    linted for style or correctness.
    """

    SRC = "src"
    LIB = "lib"
    TESTS_UNIT = "tests/unit"
    TESTS_INTEGRATION = "tests/integration"
    OTHER = "other"


@dataclasses.dataclass(frozen=True)
class Module:
    """One parsed Python file, with the provenance a diagnostic needs.

    ``path`` is charm-relative and POSIX-formatted — the form a diagnostic
    should report, matching how YAML rules report ``charmcraft.yaml``. Use
    ``file`` when an absolute path is genuinely needed (a permission check,
    say); everything user-facing wants ``path``.
    """

    path: str
    file: pathlib.Path
    text: str
    tree: ast.Module
    scope: Scope

    def walk(self, *types: type[ast.AST]) -> Iterator[Any]:
        """Yield every node of the given types, anywhere in the module.

        With no types given, yields every node.
        """
        for node in ast.walk(self.tree):
            if not types or isinstance(node, types):
                yield node

    def functions(self) -> Iterator[ast.FunctionDef | ast.AsyncFunctionDef]:
        """Yield every function and method defined anywhere in the module."""
        yield from self.walk(ast.FunctionDef, ast.AsyncFunctionDef)


@dataclasses.dataclass
class CharmContext:
    """All the data a rule needs, loaded once by the linter engine."""

    charm_dir: pathlib.Path
    # The charm's metadata, merged from charmcraft.yaml and metadata.yaml.
    # ``metadata.source`` names the file the charm's metadata primarily
    # comes from; each child node names the file that key came from, which
    # for a split-metadata charm need not be the same one.
    metadata: Yaml = dataclasses.field(default_factory=lambda: Yaml.absent("charmcraft.yaml"))
    # Declared actions, from charmcraft.yaml or legacy actions.yaml.
    actions: Yaml = dataclasses.field(default_factory=lambda: Yaml.absent("charmcraft.yaml"))
    # Declared config options, from charmcraft.yaml or legacy config.yaml.
    config_options: Yaml = dataclasses.field(
        default_factory=lambda: Yaml.absent("charmcraft.yaml")
    )
    python_files: list[pathlib.Path] = dataclasses.field(default_factory=list)
    python_sources: dict[pathlib.Path, str] = dataclasses.field(default_factory=dict)
    # Every collected source, parsed once by the linter core. Rules should
    # reach these through ``charm_sources()`` or ``modules()``, which select
    # by scope.
    python_modules: list[Module] = dataclasses.field(default_factory=list)
    readme_content: str = ""
    has_tests_unit: bool = False
    has_tests_integration: bool = False

    def modules(self, *scopes: Scope) -> Iterator[Module]:
        """Yield the parsed modules, restricted to *scopes*.

        With no scopes given, yields every module the linter collected.
        """
        for module in self.python_modules:
            if not scopes or module.scope in scopes:
                yield module

    def charm_sources(self) -> Iterator[Module]:
        """Yield the charm's own source modules — ``src/``, excluding ``lib/``.

        The default iterator for a rule that checks charm code. Vendored
        libraries are the library author's problem, and tests are a
        different question from the charm they exercise.
        """
        return self.modules(Scope.SRC)


@dataclasses.dataclass
class LintReport:
    """Aggregated lint results, bucketed by severity for O(1) counts."""

    charm_dir: pathlib.Path
    by_severity: dict[Severity, list[Diagnostic]] = dataclasses.field(
        default_factory=lambda: {s: [] for s in Severity}
    )

    @classmethod
    def from_diagnostics(
        cls, charm_dir: pathlib.Path, diagnostics: list[Diagnostic]
    ) -> "LintReport":
        """Build a report from a flat list of diagnostics."""
        report = cls(charm_dir=charm_dir)
        for d in diagnostics:
            report.by_severity[d.severity].append(d)
        return report

    def __iter__(self):
        """Yield every diagnostic in severity order (error, warning, info)."""
        for severity in Severity:
            yield from self.by_severity[severity]

    def __len__(self) -> int:
        return sum(len(bucket) for bucket in self.by_severity.values())

    @property
    def error_count(self) -> int:
        """Number of error-severity diagnostics."""
        return len(self.by_severity[Severity.ERROR])

    @property
    def warning_count(self) -> int:
        """Number of warning-severity diagnostics."""
        return len(self.by_severity[Severity.WARNING])

    @property
    def info_count(self) -> int:
        """Number of info-severity diagnostics."""
        return len(self.by_severity[Severity.INFO])

    def to_dict(self) -> dict[str, Any]:
        """Serialise the full report to a JSON-friendly dict."""
        return {
            "charm_dir": str(self.charm_dir),
            "total": len(self),
            "errors": self.error_count,
            "warnings": self.warning_count,
            "info": self.info_count,
            "diagnostics": [d.to_dict() for d in self],
        }
