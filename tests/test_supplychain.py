"""Tests for SUPPLYCHAIN rules."""

import pathlib

from charmlint._linter import lint
from charmlint._models import Severity
from charmlint._rules import supplychain as _supplychain
from tests.conftest import write_charmcraft_yaml


class TestOpsPinningRules:
    """Tests for the ops dependency pinning rules."""

    def test_supplychain005_bare_ops_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "requirements.txt").write_text("ops\n")
        report = lint(tmp_charm)
        hits = [d for d in report if d.rule_id == "SUPPLYCHAIN-005"]
        assert len(hits) == 1
        assert hits[0].severity == Severity.WARNING
        assert not [d for d in report if d.rule_id == "SUPPLYCHAIN-006"]

    def test_supplychain005_bare_ops_extras_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "requirements.txt").write_text("ops[tracing]\n")
        report = lint(tmp_charm)
        assert [d for d in report if d.rule_id == "SUPPLYCHAIN-005"]

    def test_supplychain005_bare_ops_in_pyproject_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "pyproject.toml").write_text(
            '[project]\nname = "x"\ndependencies = [\n  "ops",\n]\n'
        )
        report = lint(tmp_charm)
        assert [d for d in report if d.rule_id == "SUPPLYCHAIN-005"]

    def test_range_pin_passes(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "requirements.txt").write_text("ops>=2.23,<4\n")
        report = lint(tmp_charm)
        assert not [d for d in report if d.rule_id in {"SUPPLYCHAIN-005", "SUPPLYCHAIN-006"}]

    def test_supplychain006_exact_pin_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "requirements.txt").write_text("ops==3.7.1\n")
        report = lint(tmp_charm)
        hits = [d for d in report if d.rule_id == "SUPPLYCHAIN-006"]
        assert len(hits) == 1
        assert hits[0].severity == Severity.INFO
        assert hits[0].line == 1
        assert not [d for d in report if d.rule_id == "SUPPLYCHAIN-005"]

    def test_requirements_line_number_is_reported(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "requirements.txt").write_text("# a comment\nrequests>=2.0\n\nops==3.7.1\n")
        report = lint(tmp_charm)
        hits = [d for d in report if d.rule_id == "SUPPLYCHAIN-006"]
        assert len(hits) == 1
        assert hits[0].line == 4

    def test_supplychain006_exact_pin_in_pyproject_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "pyproject.toml").write_text('[project]\ndependencies = ["ops==3.7.1"]\n')
        report = lint(tmp_charm)
        assert [d for d in report if d.rule_id == "SUPPLYCHAIN-006"]

    def test_no_ops_dependency_not_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "requirements.txt").write_text("requests>=2.0\n")
        report = lint(tmp_charm)
        assert not [d for d in report if d.rule_id in {"SUPPLYCHAIN-005", "SUPPLYCHAIN-006"}]

    def test_pyproject_ops_in_keywords_not_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "pyproject.toml").write_text(
            "[project]\n"
            'name = "ops"\n'
            'keywords = ["ops", "charm"]\n'
            'dependencies = ["ops>=2.23,<4"]\n'
        )
        report = lint(tmp_charm)
        assert not [d for d in report if d.rule_id in {"SUPPLYCHAIN-005", "SUPPLYCHAIN-006"}]

    def test_pyproject_optional_dependencies_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "pyproject.toml").write_text(
            "[project]\n"
            'name = "x"\n'
            "dependencies = []\n"
            "\n"
            "[project.optional-dependencies]\n"
            'tracing = ["ops==3.7.1"]\n'
        )
        report = lint(tmp_charm)
        assert [d for d in report if d.rule_id == "SUPPLYCHAIN-006"]

    def test_pyproject_dependency_groups_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "pyproject.toml").write_text(
            '[project]\nname = "x"\n\n[dependency-groups]\ndev = ["ops"]\n'
        )
        report = lint(tmp_charm)
        assert [d for d in report if d.rule_id == "SUPPLYCHAIN-005"]

    def test_poetry_caret_pin_not_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "pyproject.toml").write_text(
            "[tool.poetry]\n"
            'name = "x"\n'
            "\n"
            "[tool.poetry.dependencies]\n"
            'python = "^3.10"\n'
            'ops = "^2.23"\n'
        )
        report = lint(tmp_charm)
        assert not [d for d in report if d.rule_id in {"SUPPLYCHAIN-005", "SUPPLYCHAIN-006"}]

    def test_poetry_star_unpinned_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "pyproject.toml").write_text('[tool.poetry.dependencies]\nops = "*"\n')
        report = lint(tmp_charm)
        assert [d for d in report if d.rule_id == "SUPPLYCHAIN-005"]

    def test_poetry_exact_pin_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "pyproject.toml").write_text('[tool.poetry.dependencies]\nops = "==3.7.1"\n')
        report = lint(tmp_charm)
        assert [d for d in report if d.rule_id == "SUPPLYCHAIN-006"]

    def test_poetry_table_version_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "pyproject.toml").write_text(
            '[tool.poetry.dependencies]\nops = { version = "==3.7.1", extras = ["tracing"] }\n'
        )
        report = lint(tmp_charm)
        assert [d for d in report if d.rule_id == "SUPPLYCHAIN-006"]

    def test_poetry_group_dependencies_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "pyproject.toml").write_text(
            '[tool.poetry.group.dev.dependencies]\nops = "==3.7.1"\n'
        )
        report = lint(tmp_charm)
        assert [d for d in report if d.rule_id == "SUPPLYCHAIN-006"]

    def test_malformed_pyproject_reported_as_fatal(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "pyproject.toml").write_text("this is [not valid toml\n")
        (tmp_charm / "requirements.txt").write_text("ops==3.7.1\n")
        report = lint(tmp_charm)
        # A broken pyproject.toml is reported, not silently skipped in
        # favour of requirements.txt: the charm's real dependency
        # declaration could not be read, so a clean JUJU report would be
        # a lie.
        fatal = [d for d in report if d.rule_id == "FATAL"]
        assert len(fatal) == 1
        assert "pyproject.toml" in fatal[0].message
        assert not [d for d in report if d.rule_id in {"SUPPLYCHAIN-005", "SUPPLYCHAIN-006"}]

    def test_uv_plugin_ignores_requirements_txt(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x", "parts": {"my-charm": {"plugin": "uv"}}})
        (tmp_charm / "requirements.txt").write_text("ops==3.7.1\n")
        report = lint(tmp_charm)
        assert not [d for d in report if d.rule_id in {"SUPPLYCHAIN-005", "SUPPLYCHAIN-006"}]

    def test_poetry_plugin_ignores_requirements_txt(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm, {"name": "x", "parts": {"my-charm": {"plugin": "poetry"}}}
        )
        (tmp_charm / "requirements.txt").write_text("ops\n")
        report = lint(tmp_charm)
        assert not [d for d in report if d.rule_id in {"SUPPLYCHAIN-005", "SUPPLYCHAIN-006"}]

    def test_uv_plugin_still_checks_pyproject(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x", "parts": {"my-charm": {"plugin": "uv"}}})
        (tmp_charm / "pyproject.toml").write_text(
            '[project]\nname = "x"\ndependencies = [\n  "ops==3.7.1",\n]\n'
        )
        report = lint(tmp_charm)
        assert [d for d in report if d.rule_id == "SUPPLYCHAIN-006"]

    def test_charm_plugin_still_checks_requirements_txt(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x", "parts": {"my-charm": {"plugin": "charm"}}})
        (tmp_charm / "requirements.txt").write_text("ops==3.7.1\n")
        report = lint(tmp_charm)
        assert [d for d in report if d.rule_id == "SUPPLYCHAIN-006"]


class TestOpsDependencyParsing:
    """The parsed ops dependency, which every JUJU pinning rule works from."""

    def test_pep508_specifier_extras_and_section(self):
        dep = _supplychain._parse_pep508(
            "ops[tracing,testing]>=2.23,<4", "pyproject.toml", "project.dependencies"
        )
        assert dep is not None
        assert dep.specifier == ">=2.23,<4"
        assert dep.extras == ("tracing", "testing")
        assert dep.section == "project.dependencies"
        assert dep.line is None
        assert not dep.is_unpinned
        assert not dep.is_exact

    def test_pep508_environment_marker_dropped(self):
        dep = _supplychain._parse_pep508(
            'ops>=2.23; python_version < "3.12"', "requirements.txt", "requirements.txt"
        )
        assert dep is not None
        assert dep.specifier == ">=2.23"

    def test_pep508_non_ops_ignored(self):
        assert (
            _supplychain._parse_pep508(
                "operator-libs-linux", "requirements.txt", "requirements.txt"
            )
            is None
        )

    def test_pep508_bare_is_unpinned(self):
        dep = _supplychain._parse_pep508("ops", "requirements.txt", "requirements.txt")
        assert dep is not None
        assert dep.specifier == ""
        assert dep.is_unpinned

    def test_poetry_table_keeps_version_and_extras(self):
        dep = _supplychain._parse_poetry(
            {"version": "==3.7.1", "extras": ["tracing"]},
            "pyproject.toml",
            "tool.poetry.dependencies",
        )
        assert dep.specifier == "==3.7.1"
        assert dep.extras == ("tracing",)
        assert dep.is_exact

    def test_poetry_wildcard_is_unpinned(self):
        dep = _supplychain._parse_poetry("*", "pyproject.toml", "tool.poetry.dependencies")
        assert dep.is_unpinned

    def test_section_recorded_for_optional_dependencies(self):
        dep = _supplychain._find_ops_in_pyproject(
            {"project": {"optional-dependencies": {"dev": ["ops==3.7.1"]}}}
        )
        assert dep is not None
        assert dep.section == "project.optional-dependencies.dev"

    def test_section_recorded_for_dependency_groups(self):
        dep = _supplychain._find_ops_in_pyproject({"dependency-groups": {"test": ["ops"]}})
        assert dep is not None
        assert dep.section == "dependency-groups.test"

    def test_section_recorded_for_poetry_group(self):
        dep = _supplychain._find_ops_in_pyproject(
            {"tool": {"poetry": {"group": {"dev": {"dependencies": {"ops": "==3.7.1"}}}}}}
        )
        assert dep is not None
        assert dep.section == "tool.poetry.group.dev.dependencies"

    def test_requirements_line_recorded(self, tmp_charm: pathlib.Path):
        path = tmp_charm / "requirements.txt"
        path.write_text("# a comment\n-r other.txt\n\nops==3.7.1\n")
        dep = _supplychain._find_ops_in_requirements(path)
        assert dep is not None
        assert dep.line == 4
        assert dep.section == "requirements.txt"

    def test_where_names_a_pyproject_section(self):
        dep = _supplychain._parse_pep508("ops", "pyproject.toml", "dependency-groups.test")
        assert dep is not None
        assert dep.where == " in `dependency-groups.test`"

    def test_where_empty_for_requirements(self):
        dep = _supplychain._parse_pep508("ops", "requirements.txt", "requirements.txt")
        assert dep is not None
        assert dep.where == ""


class TestSectionInMessages:
    """The section a dependency was declared in reaching the diagnostic."""

    def test_pyproject_message_names_the_section(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "pyproject.toml").write_text('[project]\ndependencies = ["ops==3.7.1"]\n')
        report = lint(tmp_charm)
        hits = [d for d in report if d.rule_id == "SUPPLYCHAIN-006"]
        assert len(hits) == 1
        assert "in `project.dependencies`" in hits[0].message

    def test_requirements_message_does_not_repeat_the_file(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "requirements.txt").write_text("ops\n")
        report = lint(tmp_charm)
        hits = [d for d in report if d.rule_id == "SUPPLYCHAIN-005"]
        assert len(hits) == 1
        assert "requirements.txt" not in hits[0].message
        assert hits[0].path == "requirements.txt"
