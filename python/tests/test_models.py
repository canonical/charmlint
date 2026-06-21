"""Tests for charmlint.models."""

import pathlib

from charmlint.models import Diagnostic, LintReport, Severity


class TestDiagnostic:
    """Tests for the Diagnostic dataclass."""

    def test_format_text_basic(self):
        d = Diagnostic(rule_id="COS001", severity=Severity.WARNING, message="Missing tracing")
        assert d.format_text() == "COS001 Missing tracing"

    def test_format_text_with_path(self):
        d = Diagnostic(
            rule_id="DEP001", severity=Severity.ERROR, message="StoredState", path="src/charm.py"
        )
        assert d.format_text() == "src/charm.py: DEP001 StoredState"

    def test_format_text_with_path_and_line(self):
        d = Diagnostic(
            rule_id="DEP001",
            severity=Severity.ERROR,
            message="StoredState",
            path="src/charm.py",
            line=42,
        )
        assert d.format_text() == "src/charm.py:42: DEP001 StoredState"

    def test_format_text_relative_to_charm_dir(self):
        d = Diagnostic(
            rule_id="DEP001",
            severity=Severity.ERROR,
            message="StoredState",
            path="/home/user/charm/src/charm.py",
        )
        result = d.format_text(charm_dir=pathlib.Path("/home/user/charm"))
        assert result == "src/charm.py: DEP001 StoredState"

    def test_to_dict(self):
        d = Diagnostic(
            rule_id="COS001",
            severity=Severity.WARNING,
            message="Missing tracing",
            path="charmcraft.yaml",
            fix_hint="Add tracing relation",
        )
        result = d.to_dict()
        assert result["rule_id"] == "COS001"
        assert result["severity"] == "warning"
        assert result["path"] == "charmcraft.yaml"
        assert result["fix_hint"] == "Add tracing relation"

    def test_to_dict_minimal(self):
        d = Diagnostic(rule_id="X", severity=Severity.INFO, message="msg")
        result = d.to_dict()
        assert "path" not in result
        assert "line" not in result
        assert "fix_hint" not in result


class TestLintReport:
    """Tests for the LintReport dataclass."""

    def test_empty_report(self):
        report = LintReport(charm_dir=pathlib.Path("/tmp/charm"))
        assert report.error_count == 0
        assert report.warning_count == 0
        assert report.info_count == 0
        assert report.summary_line() == "No issues found."

    def test_counts(self):
        report = LintReport(
            charm_dir=pathlib.Path("/tmp/charm"),
            diagnostics=[
                Diagnostic("E1", Severity.ERROR, "err1"),
                Diagnostic("E2", Severity.ERROR, "err2"),
                Diagnostic("W1", Severity.WARNING, "warn1"),
                Diagnostic("I1", Severity.INFO, "info1"),
            ],
        )
        assert report.error_count == 2
        assert report.warning_count == 1
        assert report.info_count == 1
        assert "4 issues" in report.summary_line()
        assert "2 errors" in report.summary_line()

    def test_to_dict(self):
        report = LintReport(
            charm_dir=pathlib.Path("/tmp/charm"),
            diagnostics=[Diagnostic("E1", Severity.ERROR, "err")],
        )
        result = report.to_dict()
        assert result["total"] == 1
        assert result["errors"] == 1
        assert len(result["diagnostics"]) == 1
