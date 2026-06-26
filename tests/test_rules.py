"""Tests for charmlint rules."""

import pathlib

from charmlint._linter import lint
from charmlint._models import Severity
from tests.conftest import make_full_charm, write_charmcraft_yaml


class TestMetadataRules:
    """Tests for metadata field checks."""

    def test_missing_name_is_error(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"display-name": "X"})
        report = lint(tmp_charm)
        ids = {d.rule_id for d in report.diagnostics}
        assert "META001" in ids
        meta001 = [d for d in report.diagnostics if d.rule_id == "META001"][0]
        assert meta001.severity == Severity.ERROR

    def test_full_metadata_no_meta_diagnostics(self, tmp_charm: pathlib.Path):
        make_full_charm(tmp_charm)
        report = lint(tmp_charm)
        meta_ids = {d.rule_id for d in report.diagnostics if d.rule_id.startswith("META")}
        assert not meta_ids

    def test_meta_diagnostics_path_is_charmcraft_yaml(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"display-name": "X"})
        report = lint(tmp_charm)
        meta001 = [d for d in report.diagnostics if d.rule_id == "META001"][0]
        assert meta001.path == "charmcraft.yaml"

    def test_meta_diagnostics_path_is_metadata_yaml_for_legacy_charms(
        self, tmp_charm: pathlib.Path
    ):
        (tmp_charm / "metadata.yaml").write_text("display-name: X\n")
        report = lint(tmp_charm)
        meta001 = [d for d in report.diagnostics if d.rule_id == "META001"][0]
        assert meta001.path == "metadata.yaml"

    def test_modern_charmcraft_title_and_links_satisfy_meta(self, tmp_charm: pathlib.Path):
        # Modern charmcraft.yaml uses `title` and a `links:` block instead of
        # the legacy top-level `display-name`/`docs`/`issues`/`source`.
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test-charm",
                "title": "Test Charm",
                "summary": "x",
                "description": "x",
                "links": {
                    "documentation": "https://example.com/docs",
                    "issues": "https://example.com/issues",
                    "source": "https://example.com/source",
                },
            },
        )
        report = lint(tmp_charm)
        ids = {d.rule_id for d in report.diagnostics}
        for rid in ("META002", "META005", "META006", "META007"):
            assert rid not in ids, f"{rid} should not fire for modern charmcraft.yaml"


class TestFullCharm:
    """Integration test — a well-formed charm should have minimal diagnostics."""

    def test_full_charm_minimal_issues(self, tmp_charm: pathlib.Path):
        make_full_charm(tmp_charm)
        report = lint(tmp_charm)
        assert report.error_count == 0
        for d in report.diagnostics:
            assert d.severity != Severity.ERROR, f"Unexpected error: {d.rule_id} {d.message}"
