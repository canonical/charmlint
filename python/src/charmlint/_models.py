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
    """Aggregated lint results."""

    charm_dir: pathlib.Path
    diagnostics: list[Diagnostic] = dataclasses.field(default_factory=list)

    @property
    def error_count(self) -> int:
        """Number of error-severity diagnostics."""
        return sum(1 for d in self.diagnostics if d.severity == Severity.ERROR)

    @property
    def warning_count(self) -> int:
        """Number of warning-severity diagnostics."""
        return sum(1 for d in self.diagnostics if d.severity == Severity.WARNING)

    @property
    def info_count(self) -> int:
        """Number of info-severity diagnostics."""
        return sum(1 for d in self.diagnostics if d.severity == Severity.INFO)

    def summary_line(self) -> str:
        """One-line summary of findings."""
        total = len(self.diagnostics)
        if total == 0:
            return "No issues found."
        parts = []
        if self.error_count:
            parts.append(f"{self.error_count} error{'s' if self.error_count != 1 else ''}")
        if self.warning_count:
            parts.append(f"{self.warning_count} warning{'s' if self.warning_count != 1 else ''}")
        if self.info_count:
            parts.append(f"{self.info_count} info")
        return f"Found {total} issue{'s' if total != 1 else ''} ({', '.join(parts)})"

    def to_dict(self) -> dict[str, Any]:
        """Serialise the full report to a JSON-friendly dict."""
        return {
            "charm_dir": str(self.charm_dir),
            "total": len(self.diagnostics),
            "errors": self.error_count,
            "warnings": self.warning_count,
            "info": self.info_count,
            "diagnostics": [d.to_dict() for d in self.diagnostics],
        }
