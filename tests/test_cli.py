"""Tests for charmlint._cli."""

import json
import pathlib
import re
import subprocess
import sys
import textwrap

import pytest

import charmlint
from charmlint._cli import main
from charmlint._linter import lint
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
        # --strict only changes the exit code when there are warnings and no
        # errors, so check the fixture still gives that before relying on it.
        report = lint(tmp_charm)
        assert report.error_count == 0
        assert report.warning_count > 0
        exit_code_normal = main([str(tmp_charm)])
        assert exit_code_normal == 0
        exit_code_strict = main([str(tmp_charm), "--strict"])
        assert exit_code_strict == 1

    def test_strict_mode_keeps_2_for_failing_to_run(self, tmp_charm: pathlib.Path):
        # --strict findings exit 1, so 2 still means charmlint couldn't run,
        # even on a charm whose warnings would otherwise fail the run.
        make_full_charm(tmp_charm)
        assert main([str(tmp_charm), "--strict", "--select", "NOT-A-RULE"]) == 2
        bad_config = tmp_charm / "bad.toml"
        bad_config.write_text("this is not toml = = =\n")
        assert main([str(tmp_charm), "--strict", "--config", str(bad_config)]) == 2

    def test_version(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            main(["--version"])
        assert exc_info.value.code == 0
        assert capsys.readouterr().out.startswith("charmlint ")


class TestVersionIsLazy:
    """``importlib.metadata`` must not be imported unless ``--version`` is used."""

    def test_importlib_metadata_not_imported_by_a_lint(self, tmp_charm: pathlib.Path):
        # In a subprocess, because this test session has imported plenty already.
        code = textwrap.dedent("""
            import sys
            from charmlint._cli import main
            main([sys.argv[1]])
            assert "importlib.metadata" not in sys.modules
        """)
        result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
            [sys.executable, "-c", code, str(tmp_charm)], capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr

    def test_version_attribute_still_works(self):
        assert re.match(r"\d+\.\d+", charmlint.__version__)

    def test_unknown_attribute_raises(self):
        with pytest.raises(AttributeError):
            charmlint.nonexistent  # ruff: ignore[useless-expression]
