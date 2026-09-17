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
        result = subprocess.run(
            [sys.executable, "-c", code, str(tmp_charm)], capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr

    def test_version_attribute_still_works(self):
        assert re.match(r"\d+\.\d+", charmlint.__version__)

    def test_unknown_attribute_raises(self):
        with pytest.raises(AttributeError):
            charmlint.nonexistent  # noqa: B018
