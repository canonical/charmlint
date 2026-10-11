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
        assert data["diagnostics"]
        assert {d["severity"] for d in data["diagnostics"]} == {"error"}
        # ...and there was something for the filter to remove.
        assert lint(tmp_charm).warning_count

    def test_strict_mode(self, tmp_charm: pathlib.Path):
        make_full_charm(tmp_charm)
        report = lint(tmp_charm)
        # Warnings but no errors: exactly the case --strict changes.
        assert report.warning_count and not report.error_count
        assert main([str(tmp_charm)]) == 0
        assert main([str(tmp_charm), "--strict"]) == 2

    def test_version(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            main(["--version"])
        assert exc_info.value.code == 0
        assert capsys.readouterr().out.startswith("charmlint ")


class TestCLIOptions:
    """The flags that shape output and config, each of which a test should notice breaking."""

    @pytest.fixture
    def charm(self, tmp_charm: pathlib.Path) -> pathlib.Path:
        # METADATA-001 is an error, and has a fix hint and a reference URL.
        write_charmcraft_yaml(tmp_charm, {"display-name": "X"})
        return tmp_charm

    @staticmethod
    def _as_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
        # capsys replaces stdout with something that isn't a terminal, so
        # colour is off unless we say otherwise. It only does that once the
        # test body starts, so this can't be a fixture.
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.setattr(sys.stdout, "isatty", lambda: True)

    def test_colour_on_a_terminal(self, charm: pathlib.Path, capsys, monkeypatch):
        self._as_terminal(monkeypatch)
        main([str(charm)])
        assert "\033[" in capsys.readouterr().out

    @pytest.mark.parametrize("flag", ["--no-colour", "--no-color"])
    def test_no_colour_flag(self, charm: pathlib.Path, capsys, monkeypatch, flag: str):
        self._as_terminal(monkeypatch)
        main([str(charm), flag])
        assert "\033[" not in capsys.readouterr().out

    def test_no_color_environment_variable(
        self, charm: pathlib.Path, capsys, monkeypatch: pytest.MonkeyPatch
    ):
        self._as_terminal(monkeypatch)
        monkeypatch.setenv("NO_COLOR", "1")
        main([str(charm)])
        assert "\033[" not in capsys.readouterr().out

    def test_json_is_never_coloured(self, charm: pathlib.Path, capsys, monkeypatch):
        self._as_terminal(monkeypatch)
        main([str(charm), "--format", "json"])
        json.loads(capsys.readouterr().out)

    def test_json_carries_hint_and_reference_url(self, charm: pathlib.Path, capsys):
        main([str(charm), "--format", "json", "--select", "METADATA-001"])
        [diagnostic] = json.loads(capsys.readouterr().out)["diagnostics"]
        assert diagnostic["reference_url"].startswith("https://")
        assert diagnostic["path"] == "charmcraft.yaml"

    def test_explicit_config_is_used(self, charm: pathlib.Path, tmp_path: pathlib.Path, capsys):
        config = tmp_path / "elsewhere.toml"
        config.write_text('ignore = ["METADATA-001"]\n')
        main([str(charm), "--format", "json", "--config", str(config)])
        rule_ids = {d["rule_id"] for d in json.loads(capsys.readouterr().out)["diagnostics"]}
        assert rule_ids
        assert "METADATA-001" not in rule_ids

    def test_missing_explicit_config_is_an_error(self, charm: pathlib.Path, tmp_path, capsys):
        assert main([str(charm), "--config", str(tmp_path / "nope.toml")]) == 2
        assert "nope.toml" in capsys.readouterr().err

    def test_quiet_drops_the_summary_but_not_the_findings(self, charm: pathlib.Path, capsys):
        main([str(charm)])
        loud = capsys.readouterr().out
        main([str(charm), "--quiet"])
        quiet = capsys.readouterr().out
        assert "Found " in loud
        assert "Found " not in quiet
        assert "METADATA-001" in quiet

    def test_quiet_drops_the_empty_state_message(self, tmp_charm: pathlib.Path, capsys):
        make_full_charm(tmp_charm)
        main([str(tmp_charm), "--select", "METADATA-001"])
        assert "No issues found" in capsys.readouterr().err
        main([str(tmp_charm), "--select", "METADATA-001", "--quiet"])
        assert capsys.readouterr().err == ""

    def test_verbose_names_the_config_file(self, charm: pathlib.Path, capsys):
        (charm / "charmlint.toml").write_text('ignore = ["STRUCTURE"]\n')
        main([str(charm)])
        assert "Loaded config from" not in capsys.readouterr().err
        main([str(charm), "--verbose"])
        assert f"Loaded config from {charm / 'charmlint.toml'}" in capsys.readouterr().err

    def test_python_dash_m(self, charm: pathlib.Path):
        # The exit code has to survive cli_entry's sys.exit, not just main().
        result = subprocess.run(
            [sys.executable, "-m", "charmlint", str(charm)], capture_output=True, text=True
        )
        assert result.returncode == 1, result.stderr
        assert "METADATA-001" in result.stdout


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
