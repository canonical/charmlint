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
        assert ctx.metadata["name"].value == "my-charm"

    def test_falls_back_to_metadata_yaml(self, tmp_charm: pathlib.Path):
        (tmp_charm / "metadata.yaml").write_text("name: legacy-charm\nsummary: hi\n")
        ctx = build_context(tmp_charm)
        assert ctx.metadata["name"].value == "legacy-charm"

    def test_merges_metadata_yaml_into_charmcraft_yaml(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"type": "charm", "parts": {}})
        (tmp_charm / "metadata.yaml").write_text(
            "name: split-charm\nsummary: A split charm\ndescription: Long desc\n"
        )
        ctx = build_context(tmp_charm)
        assert ctx.metadata["type"].value == "charm"
        assert ctx.metadata["name"].value == "split-charm"
        assert ctx.metadata["summary"].value == "A split charm"

    def test_charmcraft_yaml_takes_precedence_over_metadata_yaml(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "from-charmcraft", "type": "charm"})
        (tmp_charm / "metadata.yaml").write_text("name: from-metadata\nsummary: hi\n")
        ctx = build_context(tmp_charm)
        assert ctx.metadata["name"].value == "from-charmcraft"
        assert ctx.metadata["summary"].value == "hi"

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

    def test_skips_directories_named_like_python_files(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(tmp_charm, "import ops\n")
        spread = tmp_charm / "tests" / "spread" / "integration" / "test_architecture.py"
        spread.mkdir(parents=True)
        (spread / "task.yaml").write_text("summary: a spread test\n")
        ctx = build_context(tmp_charm)
        assert [p.name for p in ctx.python_files] == ["charm.py"]

    def test_directory_named_like_a_test_file_is_not_a_test(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        (tmp_charm / "tests" / "unit" / "test_charm.py").mkdir(parents=True)
        (tmp_charm / "tests" / "integration" / "test_charm.py").mkdir(parents=True)
        ctx = build_context(tmp_charm)
        assert ctx.has_tests_unit is False
        assert ctx.has_tests_integration is False

    def test_metadata_source_charmcraft_yaml(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        ctx = build_context(tmp_charm)
        assert ctx.metadata.source == "charmcraft.yaml"

    def test_metadata_source_metadata_yaml(self, tmp_charm: pathlib.Path):
        (tmp_charm / "metadata.yaml").write_text("name: legacy-charm\n")
        ctx = build_context(tmp_charm)
        assert ctx.metadata.source == "metadata.yaml"

    def test_metadata_source_metadata_yaml_when_charmcraft_yaml_absent(
        self, tmp_charm: pathlib.Path
    ):
        # When charmcraft.yaml is absent (or empty), the metadata source is
        # "metadata.yaml" regardless of whether metadata.yaml exists.
        # The linter emits a FATAL before rules run when both are absent.
        ctx = build_context(tmp_charm)
        assert ctx.metadata.source == "metadata.yaml"


class TestLintFiltering:
    """Tests for config-based rule filtering."""

    def test_select_categories(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        config = LintConfig(select=["METADATA"])
        report = lint(tmp_charm, config)
        for d in list(report):
            assert d.rule_id.startswith("METADATA"), f"Unexpected rule: {d.rule_id}"

    def test_ignore_rules(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"display-name": "X"})
        config = LintConfig(ignore=["METADATA-001"])
        report = lint(tmp_charm, config)
        assert "METADATA-001" not in {d.rule_id for d in list(report)}

    def test_severity_override(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"display-name": "X"})
        config = LintConfig(severity_overrides={"METADATA-001": "warning"})
        report = lint(tmp_charm, config)
        meta001 = [d for d in list(report) if d.rule_id == "METADATA-001"]
        assert meta001
        assert meta001[0].severity == Severity.WARNING

    def test_select_id_wins_over_ignored_category(self, tmp_charm: pathlib.Path):
        # More-specific select beats less-specific ignore.
        write_charmcraft_yaml(tmp_charm, {"display-name": "X"})
        config = LintConfig(select=["METADATA-001"], ignore=["METADATA"])
        report = lint(tmp_charm, config)
        assert "METADATA-001" in {d.rule_id for d in list(report)}

    def test_ignore_id_beats_select_category(self, tmp_charm: pathlib.Path):
        # More-specific ignore beats less-specific select.
        write_charmcraft_yaml(tmp_charm, {"display-name": "X"})
        config = LintConfig(select=["METADATA"], ignore=["METADATA-001"])
        report = lint(tmp_charm, config)
        assert "METADATA-001" not in {d.rule_id for d in list(report)}

    def test_min_severity_filter(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        config = LintConfig(min_severity=Severity.ERROR)
        report = lint(tmp_charm, config)
        for d in list(report):
            assert d.severity == Severity.ERROR

    def test_no_metadata_returns_fatal(self, tmp_path: pathlib.Path):
        charm_dir = tmp_path / "empty"
        charm_dir.mkdir()
        report = lint(charm_dir)
        assert report.error_count == 1
        assert next(iter(report)).rule_id == "FATAL"
        assert "No charmcraft.yaml" in next(iter(report)).message

    def test_select_unknown_category_returns_no_diagnostics(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        # A category that no rule produces should mute everything rather
        # than silently match a rule whose ID happens to share a prefix.
        config = LintConfig(select=["NOSUCH"])
        report = lint(tmp_charm, config)
        assert list(report) == []

    def test_ignore_long_category_does_not_match_short_prefix(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"display-name": "X"})
        # ``METADATA`` is a real category; ``METADATAA`` must not match it.
        # Confirms exact-string category matching, not prefix matching.
        config = LintConfig(ignore=["METADATAA"])
        report = lint(tmp_charm, config)
        assert any(d.rule_id.startswith("METADATA") for d in list(report))

    def test_malformed_charmcraft_yaml_returns_parse_error(self, tmp_path: pathlib.Path):
        charm_dir = tmp_path / "broken"
        charm_dir.mkdir()
        # Mapping value with a colon at top level confuses safe_load.
        (charm_dir / "charmcraft.yaml").write_text("name: foo\nbad: this: that\n")
        report = lint(charm_dir)
        assert report.error_count == 1
        diag = next(iter(report))
        assert diag.rule_id == "FATAL"
        # The misleading "No charmcraft.yaml" text must NOT appear when
        # the file is right there but malformed.
        assert "No charmcraft.yaml" not in diag.message
        assert "Could not load charmcraft.yaml" in diag.message


class TestCategoryOf:
    """Tests for the rule-ID category parser."""

    @pytest.mark.parametrize(
        ("rule_id", "expected"),
        [
            ("OBSERVABILITY-001", "OBSERVABILITY"),
            ("CHARMCRAFT-005", "CHARMCRAFT"),
            ("TESTING-003", "TESTING"),
            ("ATTESTATION-001", "ATTESTATION"),
            ("ACTIONS-007", "ACTIONS"),
        ],
    )
    def test_well_formed_ids(self, rule_id: str, expected: str):
        assert _category_of(rule_id) == expected

    @pytest.mark.parametrize(
        "rule_id",
        [
            # No trailing digits.
            "FOO",
            # Missing separator.
            "COS001",
            # Trailing letter after the digits.
            "COS-5G",
            # Digits before the dash.
            "COS9-001",
            # Digit prefix.
            "123",
            # Empty string.
            "",
            # Lowercase prefix — ID convention is uppercase only.
            "cos-001",
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
