"""Tests for charmcraft-compatible rules (CC001–CC004)."""

import pathlib
import stat

from charmlint._linter import lint
from tests.conftest import write_charm_source, write_charmcraft_yaml


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

    def test_underscore_action_param(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "actions": {
                    "backup": {
                        "description": "Run backup",
                        "params": {
                            "properties": {
                                "target_path": {"type": "string"},
                            },
                        },
                    },
                },
            },
        )
        report = lint(tmp_charm)
        cc002 = [d for d in report.diagnostics if d.rule_id == "CC002"]
        assert any("target_path" in d.message for d in cc002)


class TestEntrypoint:
    """Tests for CC003 — entrypoint existence and executable bit."""

    def test_no_dispatch_file(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        report = lint(tmp_charm)
        # No dispatch → not applicable, no diagnostic.
        assert "CC003" not in {d.rule_id for d in report.diagnostics}

    def test_missing_entrypoint(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        (tmp_charm / "dispatch").write_text("#!/bin/bash\nexec ./src/charm.py\n")
        report = lint(tmp_charm)
        assert "CC003" in {d.rule_id for d in report.diagnostics}

    def test_entrypoint_not_executable(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        (tmp_charm / "dispatch").write_text("#!/bin/bash\nexec ./src/charm.py\n")
        charm_py = tmp_charm / "src" / "charm.py"
        charm_py.write_text("#!/usr/bin/env python3\nimport ops\n")
        # Ensure NOT executable.
        charm_py.chmod(stat.S_IRUSR | stat.S_IWUSR)
        report = lint(tmp_charm)
        cc003 = [d for d in report.diagnostics if d.rule_id == "CC003"]
        assert len(cc003) == 1
        assert "not executable" in cc003[0].message

    def test_valid_entrypoint(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        (tmp_charm / "dispatch").write_text("#!/bin/bash\nexec ./src/charm.py\n")
        charm_py = tmp_charm / "src" / "charm.py"
        charm_py.write_text("#!/usr/bin/env python3\nimport ops\n")
        charm_py.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        report = lint(tmp_charm)
        assert "CC003" not in {d.rule_id for d in report.diagnostics}


class TestOpsMainCall:
    """Tests for CC004 — ops.main() call detection."""

    def test_no_ops_import(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(tmp_charm, "print('hello')\n")
        report = lint(tmp_charm)
        # Not an ops charm → not applicable.
        assert "CC004" not in {d.rule_id for d in report.diagnostics}

    def test_ops_without_main(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(tmp_charm, "import ops\n\nclass MyCharm(ops.CharmBase): pass\n")
        report = lint(tmp_charm)
        assert "CC004" in {d.rule_id for d in report.diagnostics}

    def test_ops_with_main(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            "import ops\n\nclass MyCharm(ops.CharmBase): pass\n\nops.main(MyCharm)\n",
        )
        report = lint(tmp_charm)
        assert "CC004" not in {d.rule_id for d in report.diagnostics}

    def test_main_with_class_arg(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            "from ops import main, CharmBase\n\nclass MyCharm(CharmBase): pass\n\nmain(MyCharm)\n",
        )
        report = lint(tmp_charm)
        assert "CC004" not in {d.rule_id for d in report.diagnostics}

    def test_main_non_charm_suffix(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            "from ops import main, CharmBase\n\nclass KafkaApp(CharmBase): pass\n\nmain(KafkaApp)\n",
        )
        report = lint(tmp_charm)
        assert "CC004" not in {d.rule_id for d in report.diagnostics}

    def test_main_with_keyword_args(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            "from ops import main, CharmBase\n\nclass MyCharm(CharmBase): pass\n\n"
            "main(MyCharm, use_juju_for_storage=True)\n",
        )
        report = lint(tmp_charm)
        assert "CC004" not in {d.rule_id for d in report.diagnostics}

    def test_diagnostic_includes_path(self, tmp_charm: pathlib.Path):
        # The diagnostic should point to the file that imports ops.
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(tmp_charm, "import ops\n\nclass MyCharm(ops.CharmBase): pass\n")
        report = lint(tmp_charm)
        cc004 = [d for d in report.diagnostics if d.rule_id == "CC004"]
        assert cc004, "Expected CC004 diagnostic"
        assert cc004[0].path is not None
