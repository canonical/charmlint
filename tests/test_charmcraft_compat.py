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


class TestNamingConventions:
    """Tests for CC002 — hyphens vs underscores."""

    def test_underscore_config(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "config": {"options": {"my_option": {"type": "string"}}},
            },
        )
        report = lint(tmp_charm)
        cc002 = [d for d in report.diagnostics if d.rule_id == "CC002"]
        assert len(cc002) >= 1
        assert "my_option" in cc002[0].message

    def test_hyphenated_config_ok(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "config": {"options": {"my-option": {"type": "string"}}},
            },
        )
        report = lint(tmp_charm)
        cc002 = [d for d in report.diagnostics if d.rule_id == "CC002"]
        assert not cc002

    def test_underscore_action(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "test", "actions": {"my_action": {"description": "Test"}}},
        )
        report = lint(tmp_charm)
        cc002 = [d for d in report.diagnostics if d.rule_id == "CC002"]
        assert any("my_action" in d.message for d in cc002)


class TestEntrypoint:
    """Tests for CC003 — entrypoint exists + executable."""

    def test_missing_entrypoint(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        (tmp_charm / "dispatch").write_text("#!/bin/sh\nexec ./src/charm.py\n")
        report = lint(tmp_charm)
        assert "CC003" in {d.rule_id for d in report.diagnostics}


class TestOpsMainCall:
    """Tests for CC004 — ops.main() call."""

    def test_missing_ops_main(self, tmp_charm: pathlib.Path):
        from tests.conftest import write_charm_source

        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(tmp_charm, "import ops\n\nclass C(ops.CharmBase):\n    pass\n")
        report = lint(tmp_charm)
        assert "CC004" in {d.rule_id for d in report.diagnostics}

    def test_with_ops_main_passes(self, tmp_charm: pathlib.Path):
        from tests.conftest import write_charm_source

        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            "import ops\n\nclass C(ops.CharmBase):\n    pass\n\nops.main(C)\n",
        )
        report = lint(tmp_charm)
        assert "CC004" not in {d.rule_id for d in report.diagnostics}
