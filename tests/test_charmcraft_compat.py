"""Tests for charmcraft-compatible rules."""

import pathlib

from charmlint._linter import lint
from charmlint._models import Severity
from tests.conftest import write_charmcraft_yaml


class TestDeprecatedSeries:
    """Tests for CHARMCRAFT-001 — deprecated 'series' attribute."""

    def test_series_present_is_warning(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test", "series": ["focal"]})
        report = lint(tmp_charm)
        diags = [d for d in list(report) if d.rule_id == "CHARMCRAFT-001"]
        assert len(diags) == 1
        assert diags[0].severity == Severity.WARNING
        assert diags[0].path == "charmcraft.yaml"

    def test_no_series(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        report = lint(tmp_charm)
        assert "CHARMCRAFT-001" not in {d.rule_id for d in list(report)}

    def test_series_in_legacy_metadata_yaml(self, tmp_charm: pathlib.Path):
        (tmp_charm / "metadata.yaml").write_text("name: test\nseries: [focal]\n")
        report = lint(tmp_charm)
        diags = [d for d in list(report) if d.rule_id == "CHARMCRAFT-001"]
        assert len(diags) == 1
        assert diags[0].path == "metadata.yaml"
