"""Tests for charmlint rules.

Only METADATA-001-relevant tests live here during the rules-refactor; the
other rule families are re-added alongside their PRs from
``RULES_TRACKER.md``.
"""

import pathlib

from charmlint._linter import lint
from charmlint._models import Severity
from tests.conftest import make_full_charm, write_charmcraft_yaml


class TestMetadataRules:
    """Tests for metadata field checks."""

    def test_missing_name_is_error(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"display-name": "X"})
        report = lint(tmp_charm)
        ids = {d.rule_id for d in list(report)}
        assert "METADATA-001" in ids
        meta001 = [d for d in list(report) if d.rule_id == "METADATA-001"][0]
        assert meta001.severity == Severity.ERROR

    def test_full_metadata_no_meta_diagnostics(self, tmp_charm: pathlib.Path):
        make_full_charm(tmp_charm)
        report = lint(tmp_charm)
        meta_ids = {d.rule_id for d in list(report) if d.rule_id.startswith("METADATA")}
        assert not meta_ids

    def test_meta_diagnostics_path_is_charmcraft_yaml(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"display-name": "X"})
        report = lint(tmp_charm)
        meta001 = [d for d in list(report) if d.rule_id == "METADATA-001"][0]
        assert meta001.path == "charmcraft.yaml"

    def test_meta_diagnostics_path_is_metadata_yaml_for_legacy_charms(
        self, tmp_charm: pathlib.Path
    ):
        (tmp_charm / "metadata.yaml").write_text("display-name: X\n")
        report = lint(tmp_charm)
        meta001 = [d for d in list(report) if d.rule_id == "METADATA-001"][0]
        assert meta001.path == "metadata.yaml"


class TestStructureRules:
    """Tests for structure rules."""

    def test_no_licence(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        report = lint(tmp_charm)
        assert "STRUCTURE-001" in {d.rule_id for d in report}


class TestFullCharm:
    """Integration test — a well-formed charm should have minimal diagnostics."""

    def test_full_charm_minimal_issues(self, tmp_charm: pathlib.Path):
        make_full_charm(tmp_charm)
        report = lint(tmp_charm)
        assert report.error_count == 0
        for d in list(report):
            assert d.severity != Severity.ERROR, f"Unexpected error: {d.rule_id} {d.message}"
