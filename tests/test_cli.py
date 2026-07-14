"""Tests for charmlint._cli."""

import json
import pathlib

from charmlint._cli import main
from tests.conftest import make_full_charm, write_charmcraft_yaml


class TestCLI:
    """Tests for the charmlint CLI entry point."""

    def test_nonexistent_path(self):
        exit_code = main(["/nonexistent/path"])
        assert exit_code == 2

    def test_no_metadata(self, tmp_path: pathlib.Path):
        exit_code = main([str(tmp_path)])
        assert exit_code == 1

    def test_bad_charm_returns_error(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"display-name": "X"})
        exit_code = main([str(tmp_charm)])
        # Missing ``name`` triggers METADATA-001 (error severity).
        assert exit_code == 1

    def test_good_charm_returns_zero(self, tmp_charm: pathlib.Path):
        make_full_charm(tmp_charm)
        exit_code = main([str(tmp_charm)])
        assert exit_code == 0

    def test_json_output(self, tmp_charm: pathlib.Path, capsys):
        write_charmcraft_yaml(tmp_charm, {"display-name": "X"})
        main([str(tmp_charm), "--format", "json"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "diagnostics" in data
        assert data["total"] > 0

    def test_select_filter(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"type": "bundle", "name": "test"})
        exit_code = main([str(tmp_charm), "--select", "METADATA"])
        # Bundles skip every METADATA rule, so with only METADATA selected,
        # no diagnostics → exit 0.
        assert exit_code == 0

    def test_ignore_filter(self, tmp_charm: pathlib.Path, capsys):
        write_charmcraft_yaml(tmp_charm, {"display-name": "X"})
        main([str(tmp_charm), "--format", "json", "--ignore", "METADATA-001"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        meta_diags = [d for d in data["diagnostics"] if d["rule_id"] == "METADATA-001"]
        assert not meta_diags

    def test_severity_filter(self, tmp_charm: pathlib.Path, capsys):
        write_charmcraft_yaml(tmp_charm, {"display-name": "X"})
        main([str(tmp_charm), "--format", "json", "--min-severity", "error"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        for d in data["diagnostics"]:
            assert d["severity"] == "error"

    def test_strict_mode(self, tmp_charm: pathlib.Path):
        make_full_charm(tmp_charm)
        exit_code_normal = main([str(tmp_charm)])
        assert exit_code_normal == 0
        exit_code_strict = main([str(tmp_charm), "--strict"])
        assert exit_code_strict in (0, 2)
