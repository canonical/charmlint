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


class TestNamingConventions:
    """Tests for CHARMCRAFT-002 — hyphens vs underscores."""

    def test_underscore_config_option(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "config": {"options": {"my_option": {"type": "string"}}},
            },
        )
        report = lint(tmp_charm)
        diags = [d for d in list(report) if d.rule_id == "CHARMCRAFT-002"]
        assert len(diags) == 1
        assert diags[0].severity == Severity.WARNING
        assert "my_option" in diags[0].message
        assert "my-option" in diags[0].message
        assert diags[0].path == "charmcraft.yaml"

    def test_hyphenated_config_option_ok(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "config": {"options": {"my-option": {"type": "string"}}},
            },
        )
        report = lint(tmp_charm)
        assert "CHARMCRAFT-002" not in {d.rule_id for d in list(report)}

    def test_underscore_action_name_is_ignored(self, tmp_charm: pathlib.Path):
        # Juju/charmcraft reject these outright, so charmlint doesn't need to.
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "test", "actions": {"my_action": {"description": "Test"}}},
        )
        report = lint(tmp_charm)
        assert "CHARMCRAFT-002" not in {d.rule_id for d in list(report)}

    def test_underscore_action_param_is_ignored(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "actions": {
                    "do-thing": {
                        "description": "Test",
                        "params": {"my_param": {"type": "string"}},
                    },
                },
            },
        )
        report = lint(tmp_charm)
        assert "CHARMCRAFT-002" not in {d.rule_id for d in list(report)}

    def test_empty_config_options_does_not_crash(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        (tmp_charm / "config.yaml").write_text("options:\n")
        report = lint(tmp_charm)
        assert "CHARMCRAFT-002" not in {d.rule_id for d in list(report)}
        assert "FATAL" not in {d.rule_id for d in list(report)}
