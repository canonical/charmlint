"""Tests for charmlint._formats."""

import json
import pathlib
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

from charmlint import _formats, _rules
from charmlint import _models as models
from charmlint._cli import main
from tests.conftest import write_charmcraft_yaml


@pytest.fixture(autouse=True)
def _no_github_workspace(monkeypatch: pytest.MonkeyPatch):
    # CI sets it, which would change the root the other tests' paths are relative to.
    monkeypatch.delenv("GITHUB_WORKSPACE", raising=False)


def _report(charm_dir: pathlib.Path, *diagnostics: models.Diagnostic) -> models.LintReport:
    return models.LintReport.from_diagnostics(charm_dir, list(diagnostics))


class TestGitHub:
    """Tests for the GitHub Actions annotations format."""

    def test_severity_maps_to_command(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.chdir(tmp_path)
        report = _report(
            tmp_path,
            models.Diagnostic("A-001", models.Severity.ERROR, "e", path="a.py", line=1),
            models.Diagnostic("A-002", models.Severity.WARNING, "w", path="a.py", line=2),
            models.Diagnostic("A-003", models.Severity.INFO, "i", path="a.py", line=3),
        )
        assert _formats.format_github(report).splitlines() == [
            "::error file=a.py,line=1,title=charmlint (A-001)::e",
            "::warning file=a.py,line=2,title=charmlint (A-002)::w",
            "::notice file=a.py,line=3,title=charmlint (A-003)::i",
        ]

    def test_path_is_relative_to_current_directory(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.chdir(tmp_path)
        charm_dir = tmp_path / "charms" / "foo"
        report = _report(
            charm_dir,
            models.Diagnostic("A-001", models.Severity.ERROR, "m", path="src/charm.py", line=4),
        )
        assert _formats.format_github(report) == (
            "::error file=charms/foo/src/charm.py,line=4,title=charmlint (A-001)::m"
        )

    def test_path_outside_current_directory_is_absolute(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ):
        (tmp_path / "elsewhere").mkdir()
        monkeypatch.chdir(tmp_path / "elsewhere")
        charm_dir = tmp_path / "charm"
        report = _report(
            charm_dir, models.Diagnostic("A-001", models.Severity.ERROR, "m", path="x.py")
        )
        assert _formats.format_github(report) == (
            f"::error file={_escaped(charm_dir / 'x.py')},title=charmlint (A-001)::m"
        )

    def test_path_is_relative_to_github_workspace(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ):
        # A step with ``working-directory: charms/foo`` still annotates the
        # repository path.
        charm_dir = tmp_path / "charms" / "foo"
        charm_dir.mkdir(parents=True)
        monkeypatch.setenv("GITHUB_WORKSPACE", str(tmp_path))
        monkeypatch.chdir(charm_dir)
        report = _report(
            charm_dir,
            models.Diagnostic("A-001", models.Severity.ERROR, "m", path="src/charm.py", line=4),
        )
        assert _formats.format_github(report) == (
            "::error file=charms/foo/src/charm.py,line=4,title=charmlint (A-001)::m"
        )

    def test_github_workspace_through_a_symlink(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ):
        repo = tmp_path / "repo"
        charm_dir = repo / "charms" / "foo"
        charm_dir.mkdir(parents=True)
        (tmp_path / "link").symlink_to(repo)
        monkeypatch.setenv("GITHUB_WORKSPACE", str(tmp_path / "link"))
        report = _report(
            charm_dir, models.Diagnostic("A-001", models.Severity.ERROR, "m", path="x.py")
        )
        assert (
            _formats.format_github(report)
            == "::error file=charms/foo/x.py,title=charmlint (A-001)::m"
        )

    def test_no_path_or_line(self, tmp_path: pathlib.Path):
        report = _report(tmp_path, models.Diagnostic("A-001", models.Severity.WARNING, "m"))
        assert _formats.format_github(report) == "::warning title=charmlint (A-001)::m"

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
            "::error title=charmlint (A-001)::m%0A%0Ado this%0A%0ASee https://example.com"
        )

    def test_escaping(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_path)
        report = _report(
            tmp_path,
            models.Diagnostic(
                "A-001", models.Severity.ERROR, "100% done\r\nok: yes, no", path="a,b:c.py"
            ),
        )
        assert _formats.format_github(report) == (
            "::error file=a%2Cb%3Ac.py,title=charmlint (A-001)::100%25 done%0D%0Aok: yes, no"
        )

    def test_cli_annotations_and_clean_run(
        self,
        tmp_charm: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ):
        write_charmcraft_yaml(tmp_charm, {"display-name": "X"})
        monkeypatch.chdir(tmp_charm.parent)
        assert main([tmp_charm.name, "--format", "github", "--select", "METADATA-001"]) == 1
        out = capsys.readouterr().out
        assert out.startswith("::error file=test-charm/charmcraft.yaml,")
        assert "title=charmlint (METADATA-001)::" in out
        assert main([tmp_charm.name, "--format", "github", "--select", "SECURITY-001"]) == 0
        assert capsys.readouterr().out == ""


def _escaped(path: pathlib.Path) -> str:
    return path.as_posix().replace(":", "%3A").replace(",", "%2C")


class TestSarif:
    """Tests for the SARIF format."""

    @pytest.fixture
    def log(
        self,
        tmp_charm: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> dict:
        write_charmcraft_yaml(tmp_charm, {"display-name": "X"})
        monkeypatch.chdir(tmp_charm.parent)
        assert main([tmp_charm.name, "--format", "sarif"]) == 1
        return json.loads(capsys.readouterr().out)

    def test_envelope(self, log: dict):
        assert log["version"] == "2.1.0"
        driver = log["runs"][0]["tool"]["driver"]
        assert driver["name"] == "charmlint"
        assert driver["version"]

    @pytest.mark.network
    def test_output_matches_the_sarif_schema(self, log: dict, tmp_path: pathlib.Path):
        sarif = tmp_path / "charmlint.sarif"
        sarif.write_text(json.dumps(log))
        result = subprocess.run(  # ruff: ignore[S603]
            [
                sys.executable,
                "-m",
                "check_jsonschema",
                "--schemafile",
                log["$schema"],
                str(sarif),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr

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

    def test_pathless_finding_has_no_region(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "metadata.yaml").write_text("name: x\n")
        report = _report(
            tmp_path, models.Diagnostic("A-001", models.Severity.WARNING, "m", line=3)
        )
        result = json.loads(_formats.format_sarif(report))["runs"][0]["results"][0]
        assert result["locations"][0]["physicalLocation"] == {
            "artifactLocation": {"uri": "metadata.yaml"}
        }
        assert "ruleIndex" not in result

    def test_path_outside_current_directory_is_a_file_uri(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ):
        charm_dir = tmp_path / "my charm"
        charm_dir.mkdir()
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        monkeypatch.chdir(elsewhere)
        report = _report(
            charm_dir, models.Diagnostic("A-001", models.Severity.WARNING, "m", path="a.py")
        )
        result = json.loads(_formats.format_sarif(report))["runs"][0]["results"][0]
        assert result["locations"][0]["physicalLocation"] == {
            "artifactLocation": {"uri": (charm_dir / "a.py").as_uri()}
        }

    def test_path_is_relative_to_github_workspace(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ):
        charm_dir = tmp_path / "charms" / "foo"
        charm_dir.mkdir(parents=True)
        monkeypatch.setenv("GITHUB_WORKSPACE", str(tmp_path))
        monkeypatch.chdir(charm_dir)
        report = _report(
            charm_dir, models.Diagnostic("A-001", models.Severity.WARNING, "m", path="a.py")
        )
        result = json.loads(_formats.format_sarif(report))["runs"][0]["results"][0]
        assert result["locations"][0]["physicalLocation"] == {
            "artifactLocation": {"uri": "charms/foo/a.py"}
        }

    def test_fix_hint_and_reference_url(self, tmp_path: pathlib.Path):
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
        result = json.loads(_formats.format_sarif(report))["runs"][0]["results"][0]
        assert result["message"] == {"text": "m\n\ndo this\n\nSee https://example.com"}

    def test_pathless_finding_without_metadata_has_no_location(self, tmp_path: pathlib.Path):
        report = _report(tmp_path, models.Diagnostic("FATAL", models.Severity.ERROR, "m"))
        result = json.loads(_formats.format_sarif(report))["runs"][0]["results"][0]
        assert "locations" not in result

    def test_pathless_finding_in_a_monorepo_says_which_charm(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ):
        for name in ("foo", "bar"):
            charm_dir = tmp_path / "charms" / name
            charm_dir.mkdir(parents=True)
            write_charmcraft_yaml(charm_dir, {"name": name})
        monkeypatch.chdir(tmp_path)
        main([".", "--format", "sarif", "--select", "STRUCTURE-001"])
        results = json.loads(capsys.readouterr().out)["runs"][0]["results"]
        uris = {r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] for r in results}
        assert uris == {"charms/foo/charmcraft.yaml", "charms/bar/charmcraft.yaml"}


class TestJunit:
    """Tests for the JUnit format."""

    @staticmethod
    def _run(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, ET.Element]:
        code = main([*args, "--format", "junit"])
        return code, ET.fromstring(capsys.readouterr().out)

    @staticmethod
    def _case(root: ET.Element, rule_id: str) -> ET.Element:
        [case] = [c for c in root.iter("testcase") if c.get("name") == f"charmlint/{rule_id}"]
        return case

    @pytest.fixture
    def charm(self, tmp_charm: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> str:
        # No name, summary or description (errors), no README (a warning)
        # and no licence (info).
        write_charmcraft_yaml(tmp_charm, {"display-name": "X"})
        monkeypatch.chdir(tmp_charm.parent)
        return tmp_charm.name

    def test_a_test_case_per_registered_rule(self, charm: str, capsys: pytest.CaptureFixture[str]):
        _, root = self._run(capsys, charm)
        [suite] = root.iter("testsuite")
        names = [case.get("name") for case in suite.iter("testcase")]
        assert names == ["charmlint/FATAL"] + [
            f"charmlint/{rule_id}" for rule_id in sorted(_rules.get_all_rules())
        ]
        assert {case.get("classname") for case in suite.iter("testcase")} == {"charmlint"}

    def test_counts(self, charm: str, capsys: pytest.CaptureFixture[str]):
        _, root = self._run(capsys, charm, "--ignore", "TESTING")
        [suite] = root.iter("testsuite")
        cases = list(suite.iter("testcase"))
        for element in (root, suite):
            assert element.get("tests") == str(len(cases))
            for attribute, outcome in (
                ("failures", "failure"),
                ("errors", "error"),
                ("skipped", "skipped"),
            ):
                expected = sum(case.find(outcome) is not None for case in cases)
                assert element.get(attribute) == str(expected)
        assert suite.get("failures") == "3"
        assert suite.get("skipped") == str(
            sum(r.startswith("TESTING") for r in _rules.get_all_rules())
        )

    def test_suite_says_which_charm_and_version(
        self, charm: str, capsys: pytest.CaptureFixture[str]
    ):
        _, root = self._run(capsys, charm)
        [suite] = root.iter("testsuite")
        properties = {p.get("name"): p.get("value") for p in suite.iter("property")}
        assert properties["charmlint.path"] == "."
        assert properties["charmlint.version"]

    def test_error_fails_its_test_case(self, charm: str, capsys: pytest.CaptureFixture[str]):
        code, root = self._run(capsys, charm)
        assert code == 1
        failure = self._case(root, "METADATA-001").find("failure")
        assert failure is not None
        assert failure.get("message") == "1 error"
        assert failure.get("type") == "error"

    def test_findings_are_in_system_out(self, charm: str, capsys: pytest.CaptureFixture[str]):
        _, root = self._run(capsys, charm)
        output = self._case(root, "METADATA-001").findtext("system-out")
        assert output is not None
        assert output.startswith("test-charm/charmcraft.yaml: error: Empty or missing 'name'")
        assert "\n    See https://" in output

    def test_warning_fails_only_with_strict(self, charm: str, capsys: pytest.CaptureFixture[str]):
        _, root = self._run(capsys, charm)
        case = self._case(root, "DOCUMENTATION-001")
        assert case.find("failure") is None
        assert case.findtext("system-out") == "warning: No README file found"

        _, root = self._run(capsys, charm, "--strict")
        failure = self._case(root, "DOCUMENTATION-001").find("failure")
        assert failure is not None
        assert failure.get("message") == "1 warning"
        assert failure.get("type") == "warning"

    def test_info_passes_with_its_finding_in_system_out(
        self, charm: str, capsys: pytest.CaptureFixture[str]
    ):
        _, root = self._run(capsys, charm, "--strict")
        case = self._case(root, "STRUCTURE-001")
        assert [child.tag for child in case] == ["system-out"]

    def test_clean_rule_has_no_children(self, charm: str, capsys: pytest.CaptureFixture[str]):
        _, root = self._run(capsys, charm)
        assert list(self._case(root, "SECURITY-001")) == []
        assert list(self._case(root, "FATAL")) == []

    def test_rule_that_did_not_run_is_skipped(
        self, charm: str, capsys: pytest.CaptureFixture[str]
    ):
        _, root = self._run(capsys, charm, "--select", "METADATA")
        skipped = self._case(root, "SECURITY-001").find("skipped")
        assert skipped is not None
        assert skipped.get("message") == "not selected"
        assert self._case(root, "METADATA-001").find("skipped") is None

    def test_rule_below_the_minimum_severity_passes(
        self, charm: str, capsys: pytest.CaptureFixture[str]
    ):
        _, root = self._run(capsys, charm, "--min-severity", "error")
        assert list(self._case(root, "STRUCTURE-001")) == []

    def test_suppressed_finding_passes(
        self,
        tmp_charm: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ):
        (tmp_charm / "charmcraft.yaml").write_text(
            "# charmlint: file-ignore[METADATA-001]\nsummary: no name\n"
        )
        monkeypatch.chdir(tmp_charm.parent)
        _, root = self._run(capsys, tmp_charm.name)
        assert list(self._case(root, "METADATA-001")) == []

    def test_charm_that_does_not_load(
        self,
        tmp_charm: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ):
        (tmp_charm / "charmcraft.yaml").write_text("name: [unclosed\n")
        monkeypatch.chdir(tmp_charm.parent)
        code, root = self._run(capsys, tmp_charm.name)
        assert code == 1
        error = self._case(root, "FATAL").find("error")
        assert error is not None
        assert error.get("message", "").startswith("Could not load charmcraft.yaml")
        cases = [c for c in root.iter("testcase") if c.get("name") != "charmlint/FATAL"]
        messages = {s.get("message") for c in cases for s in c.findall("skipped")}
        assert messages == {"the charm could not be loaded"}
        assert all(len(c.findall("skipped")) == 1 for c in cases)

    def test_no_charm_found(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ):
        monkeypatch.chdir(tmp_path)
        code, root = self._run(capsys, ".")
        assert code == 1
        assert self._case(root, "FATAL").find("error") is not None

    def test_a_suite_per_charm_in_a_monorepo(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ):
        for name in ("foo", "bar"):
            charm_dir = tmp_path / "charms" / name
            charm_dir.mkdir(parents=True)
            write_charmcraft_yaml(charm_dir, {"summary": "no name"})
        monkeypatch.chdir(tmp_path)
        _, root = self._run(capsys, ".", "--select", "METADATA-001")
        suites = list(root.iter("testsuite"))
        assert [s.get("name") for s in suites] == ["charmlint", "charmlint"]
        for suite, name in zip(suites, ("bar", "foo"), strict=True):
            [path] = [
                p.get("value") for p in suite.iter("property") if p.get("name") == "charmlint.path"
            ]
            assert path == f"charms/{name}"
            output = self._case(suite, "METADATA-001").findtext("system-out") or ""
            assert output.startswith(f"charms/{name}/charmcraft.yaml: error:")

    def test_characters_xml_cannot_hold_are_replaced(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.chdir(tmp_path)
        finding = models.Diagnostic(
            "METADATA-001", models.Severity.ERROR, "bad \x01 byte, café", path="a\x02.yaml"
        )
        report = models.LintReport.from_runs(
            tmp_path,
            [
                models.CharmRun(
                    ".", loaded=True, rules_run=frozenset({"METADATA-001"}), diagnostics=(finding,)
                )
            ],
        )
        text = _formats.format_junit(report)
        assert text.isascii()
        output = self._case(ET.fromstring(text), "METADATA-001").findtext("system-out")
        assert output == "a\ufffd.yaml: error: bad \ufffd byte, café"

    def test_same_charm_gives_the_same_output(
        self, charm: str, capsys: pytest.CaptureFixture[str]
    ):
        main([charm, "--format", "junit"])
        first = capsys.readouterr().out
        main([charm, "--format", "junit"])
        assert capsys.readouterr().out == first

    def test_test_observer_results(self, charm: str, capsys: pytest.CaptureFixture[str]):
        # What canonical/charm-integration-testing's post-results action
        # sends to Test Observer, for the cases that matter.
        _, root = self._run(capsys, charm, "--select", "METADATA,DOCUMENTATION")
        results = {r["name"]: r for r in _test_observer_results(root)}
        assert results["charmlint/METADATA-001"] == {
            "name": "charmlint/METADATA-001",
            "status": "FAILED",
            "template_id": "charmlint",
            "category": "charmlint",
            "comment": "1 error",
            "io_log": results["charmlint/METADATA-001"]["io_log"],
        }
        assert "missing 'name'" in results["charmlint/METADATA-001"]["io_log"]
        assert results["charmlint/DOCUMENTATION-001"]["status"] == "PASSED"
        assert results["charmlint/DOCUMENTATION-001"]["io_log"] == "warning: No README file found"
        assert results["charmlint/SECURITY-001"]["status"] == "SKIPPED"
        assert results["charmlint/SECURITY-001"]["comment"] == "not selected"
        assert results["charmlint/FATAL"]["status"] == "PASSED"


def _test_observer_results(root: ET.Element) -> list[dict[str, str]]:
    """Map JUnit onto Test Observer results as its charm upload action does.

    A transcription of the yq and jq in canonical/charm-integration-testing's
    ``.github/actions/test-observer/post-results/action.yaml``.
    """
    results: list[dict[str, str]] = []
    for suite in root.iter("testsuite"):
        for case in suite.iter("testcase"):
            outcomes = case.findall("error") + case.findall("failure") + case.findall("skipped")
            if case.findall("error") or case.findall("failure"):
                status = "FAILED"
            elif case.findall("skipped"):
                status = "SKIPPED"
            else:
                status = "PASSED"
            results.append({
                "name": case.get("name", ""),
                "status": status,
                "template_id": case.get("classname", ""),
                "category": suite.get("name", ""),
                "comment": ", ".join(o.get("message", "") for o in outcomes),
                "io_log": "\n".join(o.text or "" for o in case.findall("system-out")),
            })
    return results
