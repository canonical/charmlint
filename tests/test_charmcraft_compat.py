"""Tests for charmcraft-compatible rules (CC001–CC004)."""

import pathlib

from charmlint._linter import lint
from tests.conftest import write_charmcraft_yaml


class TestDeprecatedSeries:
    """Tests for CC001 — deprecated 'series' attribute."""

    def test_series_present(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test", "series": ["focal"]})
        report = lint(tmp_charm)
        assert "CC001" in {d.rule_id for d in report.diagnostics}

    def test_no_series(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        report = lint(tmp_charm)
        assert "CC001" not in {d.rule_id for d in report.diagnostics}
