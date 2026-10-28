"""Tests for charmlint._formats."""

import json
import pathlib

import pytest

from charmlint import _formats
from charmlint import _models as models
from charmlint._cli import main
from tests.conftest import write_charmcraft_yaml


def _report(charm_dir: pathlib.Path, *diagnostics: models.Diagnostic) -> models.LintReport:
    return models.LintReport.from_diagnostics(charm_dir, list(diagnostics))


class TestGitHub:
    """Tests for the GitHub Actions annotations format."""

    def test_severity_maps_to_command(self, tmp_path: pathlib.Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        report = _report(
            tmp_path,
            models.Diagnostic("A-001", models.Severity.ERROR, "e", path="a.py", line=1),
            models.Diagnostic("A-002", models.Severity.WARNING, "w", path="a.py", line=2),
            models.Diagnostic("A-003", models.Severity.INFO, "i", path="a.py", line=3),
        )
        assert _formats.format_github(report).splitlines() == [
            "::error file=a.py,line=1,title=A-001::e",
            "::warning file=a.py,line=2,title=A-002::w",
            "::notice file=a.py,line=3,title=A-003::i",
        ]

    def test_path_is_relative_to_current_directory(self, tmp_path: pathlib.Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        charm_dir = tmp_path / "charms" / "foo"
        report = _report(
            charm_dir,
            models.Diagnostic("A-001", models.Severity.ERROR, "m", path="src/charm.py", line=4),
        )
        assert _formats.format_github(report) == (
            "::error file=charms/foo/src/charm.py,line=4,title=A-001::m"
        )

    def test_path_outside_current_directory_is_absolute(self, tmp_path: pathlib.Path, monkeypatch):
        (tmp_path / "elsewhere").mkdir()
        monkeypatch.chdir(tmp_path / "elsewhere")
        charm_dir = tmp_path / "charm"
        report = _report(
            charm_dir, models.Diagnostic("A-001", models.Severity.ERROR, "m", path="x.py")
        )
        assert _formats.format_github(report) == (
            f"::error file={_escaped(charm_dir / 'x.py')},title=A-001::m"
        )

    def test_no_path_or_line(self, tmp_path: pathlib.Path):
        report = _report(tmp_path, models.Diagnostic("A-001", models.Severity.WARNING, "m"))
        assert _formats.format_github(report) == "::warning title=A-001::m"

    def test_hint_and_reference_on_following_lines(self, tmp_path: pathlib.Path):
        report = _report(
            tmp_path,
            models.Diagnostic(
                "A-001",
                models.Severity.ERROR,
                "m",
                fix_hint="do this",
                reference_url="https://example.com",
            ),
        )
        assert _formats.format_github(report) == (
            "::error title=A-001::m%0AFix: do this%0ASee https://example.com"
        )

    def test_escaping(self, tmp_path: pathlib.Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        report = _report(
            tmp_path,
            models.Diagnostic(
                "A-001", models.Severity.ERROR, "100% done\r\nok: yes, no", path="a,b:c.py"
            ),
        )
        assert _formats.format_github(report) == (
            "::error file=a%2Cb%3Ac.py,title=A-001::100%25 done%0D%0Aok: yes, no"
        )

    def test_cli_annotations_and_clean_run(self, tmp_charm: pathlib.Path, monkeypatch, capsys):
        write_charmcraft_yaml(tmp_charm, {"display-name": "X"})
        monkeypatch.chdir(tmp_charm.parent)
        assert main([tmp_charm.name, "--format", "github", "--select", "METADATA-001"]) == 1
        out = capsys.readouterr().out
        assert out.startswith("::error file=test-charm/charmcraft.yaml,")
        assert "title=METADATA-001::" in out
        assert main([tmp_charm.name, "--format", "github", "--select", "SECURITY-001"]) == 0
        assert capsys.readouterr().out == ""


def _escaped(path: pathlib.Path) -> str:
    return path.as_posix().replace(":", "%3A").replace(",", "%2C")


class TestSarif:
    """Tests for the SARIF format."""

    @pytest.fixture
    def log(self, tmp_charm: pathlib.Path, monkeypatch, capsys) -> dict:
        write_charmcraft_yaml(tmp_charm, {"display-name": "X"})
        monkeypatch.chdir(tmp_charm.parent)
        assert main([tmp_charm.name, "--format", "sarif"]) == 1
        return json.loads(capsys.readouterr().out)

    def test_envelope(self, log: dict):
        assert log["version"] == "2.1.0"
        driver = log["runs"][0]["tool"]["driver"]
        assert driver["name"] == "charmlint"
        assert driver["version"]

    def test_rules_describe_every_registered_rule(self, log: dict):
        from charmlint._rules import get_all_rules

        rules = log["runs"][0]["tool"]["driver"]["rules"]
        assert [r["id"] for r in rules] == sorted(get_all_rules())
        for rule in rules:
            assert rule["shortDescription"]["text"]
            assert rule["fullDescription"]["text"]
            assert rule["help"]["text"]
            assert rule["defaultConfiguration"]["level"] in {"error", "warning", "note"}

    def test_results_reference_their_rule(self, log: dict):
        run = log["runs"][0]
        rules = run["tool"]["driver"]["rules"]
        results = run["results"]
        assert results
        for result in results:
            assert rules[result["ruleIndex"]]["id"] == result["ruleId"]

    def test_result_location_is_relative_to_current_directory(self, log: dict):
        result = next(r for r in log["runs"][0]["results"] if r["ruleId"] == "METADATA-001")
        location = result["locations"][0]["physicalLocation"]
        assert location["artifactLocation"]["uri"] == "test-charm/charmcraft.yaml"
        assert result["level"] == "error"

    def test_every_result_has_a_location(self, log: dict):
        # Code scanning drops results without one, so findings about the
        # charm as a whole are anchored to its metadata file.
        for result in log["runs"][0]["results"]:
            assert result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]

    def test_pathless_finding_has_no_region(self, tmp_path: pathlib.Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "metadata.yaml").write_text("name: x\n")
        report = _report(
            tmp_path, models.Diagnostic("A-001", models.Severity.WARNING, "m", line=3)
        )
        result = json.loads(_formats.format_sarif(report))["runs"][0]["results"][0]
        assert result["locations"][0]["physicalLocation"] == {
            "artifactLocation": {"uri": "metadata.yaml", "uriBaseId": "%SRCROOT%"}
        }
        assert "ruleIndex" not in result

    def test_pathless_finding_without_metadata_has_no_location(self, tmp_path: pathlib.Path):
        report = _report(tmp_path, models.Diagnostic("FATAL", models.Severity.ERROR, "m"))
        result = json.loads(_formats.format_sarif(report))["runs"][0]["results"][0]
        assert "locations" not in result
