"""Core data models for charmlint."""

import contextlib
import dataclasses
import enum
import pathlib
from typing import Any


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
        return result


@dataclasses.dataclass
class CharmContext:
    """All the data a rule needs, loaded once by the linter engine."""

    charm_dir: pathlib.Path
    metadata_source: str = "charmcraft.yaml"
    metadata: dict[str, Any] = dataclasses.field(default_factory=dict)
    actions: dict[str, Any] = dataclasses.field(default_factory=dict)
    config_options: dict[str, Any] = dataclasses.field(default_factory=dict)
    python_files: list[pathlib.Path] = dataclasses.field(default_factory=list)
    python_sources: dict[pathlib.Path, str] = dataclasses.field(default_factory=dict)
    readme_content: str = ""
    has_tests_unit: bool = False
    has_tests_integration: bool = False


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
