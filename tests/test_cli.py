"""Tests for charmlint._cli."""

import argparse
import importlib
import json
import pathlib
import subprocess
import sys

import pytest

from charmlint import _cli
from charmlint._cli import main
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
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        exit_code = main([str(tmp_charm), "--select", "METADATA"])
        # Name is present so METADATA-001 doesn't fire; with only METADATA selected,
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
        main([str(tmp_charm), "--format", "json", "--severity", "error"])
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
        with pytest.raises(SystemExit) as excinfo:
            main(["--version"])
        assert excinfo.value.code == 0
        out = capsys.readouterr().out
        assert out.startswith("charmlint ")
        # A version number follows the program name.
        assert out.split()[1][0].isdigit()

    def test_text_output_format(self, tmp_charm: pathlib.Path, capsys):
        # Pin the ruff-style "location: RULE message" line format.
        write_charmcraft_yaml(tmp_charm, {"display-name": "X"})
        main([str(tmp_charm)])
        out = capsys.readouterr().out
        assert "charmcraft.yaml: META001 " in out
        assert "Found 1 issue" in out


class TestColourResolution:
    """Tests for _colour_enabled — flag > NO_COLOR > FORCE_COLOR > TTY."""

    @staticmethod
    def _args(no_colour: bool = False, output_format: str = "text") -> argparse.Namespace:
        return argparse.Namespace(no_colour=no_colour, output_format=output_format)

    @pytest.fixture(autouse=True)
    def _clean_env(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.delenv("FORCE_COLOR", raising=False)

    def test_tty_detection(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
        assert _cli._colour_enabled(self._args()) is True
        monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
        assert _cli._colour_enabled(self._args()) is False

    def test_flag_disables(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
        assert _cli._colour_enabled(self._args(no_colour=True)) is False

    def test_json_disables(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
        assert _cli._colour_enabled(self._args(output_format="json")) is False

    def test_no_color_env(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
        monkeypatch.setenv("NO_COLOR", "1")
        assert _cli._colour_enabled(self._args()) is False

    def test_force_color_env(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
        monkeypatch.setenv("FORCE_COLOR", "1")
        assert _cli._colour_enabled(self._args()) is True

    def test_no_color_beats_force_color(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
        monkeypatch.setenv("NO_COLOR", "1")
        monkeypatch.setenv("FORCE_COLOR", "1")
        assert _cli._colour_enabled(self._args()) is False

    def test_no_color_alias(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        # The US spelling parses and behaves like --no-colour.
        assert main([str(tmp_charm), "--no-color"]) == 0


class TestMainModule:
    """Tests for python -m charmlint."""

    def test_import_does_not_run_cli(self):
        # Importing the module (e.g. by inspection tooling) must not
        # parse sys.argv or exit the process.
        importlib.import_module("charmlint.__main__")

    def test_python_m_invocation(self, tmp_charm: pathlib.Path):
        make_full_charm(tmp_charm)
        proc = subprocess.run(
            [sys.executable, "-m", "charmlint", str(tmp_charm)],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr
        assert "No issues found." in proc.stdout
