"""Tests for charmlint._linter."""

import pathlib

import pytest

from charmlint._config import LintConfig
from charmlint._linter import _category_of, build_context, lint
from charmlint._models import Severity
from tests.conftest import (
    make_full_charm,
    write_charm_source,
    write_charmcraft_yaml,
)


class TestBuildContext:
    """Tests for context loading."""

    def test_loads_metadata(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "my-charm"})
        ctx = build_context(tmp_charm)
        assert ctx.metadata["name"] == "my-charm"

    def test_loads_actions(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "test", "actions": {"backup": {"description": "Run backup"}}},
        )
        ctx = build_context(tmp_charm)
        assert "backup" in ctx.actions

    def test_loads_python_sources(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(tmp_charm, "import ops\n")
        ctx = build_context(tmp_charm)
        assert len(ctx.python_files) == 1
        assert len(ctx.python_sources) == 1

    def test_detects_tests(self, tmp_charm: pathlib.Path):
        make_full_charm(tmp_charm)
        ctx = build_context(tmp_charm)
        assert ctx.has_tests_unit is True
        assert ctx.has_tests_integration is True

    def test_no_tests(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        ctx = build_context(tmp_charm)
        assert ctx.has_tests_unit is False
        assert ctx.has_tests_integration is False


class TestLintFiltering:
    """Tests for config-based rule filtering."""

    def test_select_categories(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        config = LintConfig(select=["META"])
        report = lint(tmp_charm, config)
        for d in report.diagnostics:
            assert d.rule_id.startswith("META"), f"Unexpected rule: {d.rule_id}"

    def test_ignore_rules(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        config = LintConfig(ignore=["TEST001"])
        report = lint(tmp_charm, config)
        assert "TEST001" not in {d.rule_id for d in report.diagnostics}

    def test_severity_override(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        config = LintConfig(severity_overrides={"COS001": "error"})
        report = lint(tmp_charm, config)
        cos001 = [d for d in report.diagnostics if d.rule_id == "COS001"]
        assert cos001
        assert cos001[0].severity == Severity.ERROR

    def test_disable_rule(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        config = LintConfig(severity_overrides={"COS001": "off"})
        report = lint(tmp_charm, config)
        assert "COS001" not in {d.rule_id for d in report.diagnostics}

    def test_min_severity_filter(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        config = LintConfig(min_severity=Severity.ERROR)
        report = lint(tmp_charm, config)
        for d in report.diagnostics:
            assert d.severity == Severity.ERROR

    def test_no_metadata_returns_fatal(self, tmp_path: pathlib.Path):
        charm_dir = tmp_path / "empty"
        charm_dir.mkdir()
        report = lint(charm_dir)
        assert report.error_count == 1
        assert report.diagnostics[0].rule_id == "FATAL"
        assert "No charmcraft.yaml" in report.diagnostics[0].message

    def test_select_unknown_category_returns_no_diagnostics(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        # A category that no rule produces should mute everything rather
        # than silently match a rule whose ID happens to share a prefix.
        config = LintConfig(select=["NOSUCH"])
        report = lint(tmp_charm, config)
        assert report.diagnostics == []

    def test_ignore_long_category_does_not_match_short_prefix(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        # ``COS`` is a real category; ``COSS`` must not match it.
        # Confirms exact-string category matching, not prefix matching.
        config = LintConfig(ignore=["COSS"])
        report = lint(tmp_charm, config)
        assert any(d.rule_id.startswith("COS") for d in report.diagnostics)

    def test_malformed_charmcraft_yaml_returns_parse_error(self, tmp_path: pathlib.Path):
        charm_dir = tmp_path / "broken"
        charm_dir.mkdir()
        # Mapping value with a colon at top level confuses safe_load.
        (charm_dir / "charmcraft.yaml").write_text("name: foo\nbad: this: that\n")
        report = lint(charm_dir)
        assert report.error_count == 1
        diag = report.diagnostics[0]
        assert diag.rule_id == "FATAL"
        # The misleading "No charmcraft.yaml" text must NOT appear when
        # the file is right there but malformed.
        assert "No charmcraft.yaml" not in diag.message
        assert "Could not parse charmcraft.yaml" in diag.message


class TestCategoryOf:
    """Tests for the rule-ID category parser."""

    @pytest.mark.parametrize(
        ("rule_id", "expected"),
        [
            ("COS001", "COS"),
            ("CC005", "CC"),
            ("TEST003", "TEST"),
            ("ATT001", "ATT"),
            ("ACT007", "ACT"),
        ],
    )
    def test_well_formed_ids(self, rule_id: str, expected: str):
        assert _category_of(rule_id) == expected

    @pytest.mark.parametrize(
        "rule_id",
        [
            # No trailing digits.
            "FOO",
            # Embedded digit followed by trailing letter — would have
            # been mishandled by the old rstrip-based parser, which
            # stripped only the trailing digits and produced a category
            # that depended on what happened to be at the end.
            "COS5G",
            # Mixed digits and letters — same hazard.
            "COS01A",
            # Digit prefix.
            "123",
            # Empty string.
            "",
            # Lowercase prefix — ID convention is uppercase only.
            "cos001",
        ],
    )
    def test_unrecognised_ids_round_trip(self, rule_id: str):
        # An unrecognised ID returns itself so it cannot accidentally
        # match a real category in select / ignore.
        assert _category_of(rule_id) == rule_id

    def test_real_registered_rules_round_trip(self):
        # Every registered rule's ID must extract to a non-empty
        # category string — guard against future IDs that drift from
        # the convention.
        from charmlint._rules import get_all_rules

        for rule_id in get_all_rules():
            category = _category_of(rule_id)
            assert category
            assert category != rule_id, f"{rule_id} did not produce a category"
            assert rule_id.startswith(category)
