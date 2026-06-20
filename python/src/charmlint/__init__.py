"""charmlint — a deterministic linter for Juju charms.

Public API::

    from charmlint import lint, Diagnostic, Severity, LintReport, LintConfig

    report = lint(Path("/path/to/charm"))
    for d in report.diagnostics:
        print(d.format_text())
"""

# Re-exports for the public API.
from charmlint.config import LintConfig
from charmlint.linter import lint
from charmlint.models import Diagnostic, LintReport, Severity

__all__ = [
    "Diagnostic",
    "LintConfig",
    "LintReport",
    "Severity",
    "lint",
]
