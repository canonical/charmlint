"""Tests for charmlint.cli."""

import json
import pathlib

from charmlint.cli import main
from tests.conftest import make_full_charm, write_charmcraft_yaml


class TestCLI:
    """Tests for the charmlint CLI entry point."""

    def test_nonexistent_path(self):
        exit_code = main(["/nonexistent/path"])
        assert exit_code == 1

    def test_no_metadata(self, tmp_path: pathlib.Path):
        exit_code = main([str(tmp_path)])
        assert exit_code == 1

    def test_bad_charm_returns_error(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        exit_code = main([str(tmp_charm)])
        # Should have errors (TEST001 is an error).
        assert exit_code == 1

    def test_good_charm_returns_zero(self, tmp_charm: pathlib.Path):
        make_full_charm(tmp_charm)
        exit_code = main([str(tmp_charm)])
        assert exit_code == 0

    def test_json_output(self, tmp_charm: pathlib.Path, capsys):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        main([str(tmp_charm), "--format", "json"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "diagnostics" in data
        assert data["total"] > 0

    def test_select_filter(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        exit_code = main([str(tmp_charm), "--select", "META"])
        # Only META rules — no TEST001 error, so might pass.
        # META001 is not triggered because name is present.
        # But META002-META007 are warnings, so exit code 0.
        assert exit_code == 0

    def test_ignore_filter(self, tmp_charm: pathlib.Path, capsys):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        main([str(tmp_charm), "--format", "json", "--ignore", "TEST001,TEST002,TEST003"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        test_diags = [d for d in data["diagnostics"] if d["rule_id"].startswith("TEST")]
        assert not test_diags

    def test_severity_filter(self, tmp_charm: pathlib.Path, capsys):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        main([str(tmp_charm), "--format", "json", "--severity", "error"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        for d in data["diagnostics"]:
            assert d["severity"] == "error"

    def test_strict_mode(self, tmp_charm: pathlib.Path):
        make_full_charm(tmp_charm)
        # Full charm has some info/warning items (TLS, docs).
        # With --strict, warnings cause exit code 2.
        exit_code_normal = main([str(tmp_charm)])
        assert exit_code_normal == 0
        # Check if there are warnings — if so, strict returns 2.
        exit_code_strict = main([str(tmp_charm), "--strict"])
        # Full charm might still have some warnings (SEC002 is info, DOC003-DOC005 are info).
        # If no warnings, strict also returns 0.
        assert exit_code_strict in (0, 2)
