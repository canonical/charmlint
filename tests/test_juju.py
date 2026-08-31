"""Tests for JUJU rules."""

import pathlib

from charmlint._linter import lint
from charmlint._models import Severity
from tests.conftest import write_charmcraft_yaml


class TestJujuRules:
    """Tests for JUJU (Juju-ness / idiomatic ops) rules."""

    def test_juju003_bare_ops_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "requirements.txt").write_text("ops\n")
        report = lint(tmp_charm)
        hits = [d for d in report if d.rule_id == "JUJU-003"]
        assert len(hits) == 1
        assert hits[0].severity == Severity.WARNING
        assert not [d for d in report if d.rule_id == "JUJU-004"]

    def test_juju003_bare_ops_extras_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "requirements.txt").write_text("ops[tracing]\n")
        report = lint(tmp_charm)
        assert [d for d in report if d.rule_id == "JUJU-003"]

    def test_juju003_bare_ops_in_pyproject_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "pyproject.toml").write_text(
            '[project]\nname = "x"\ndependencies = [\n  "ops",\n]\n'
        )
        report = lint(tmp_charm)
        assert [d for d in report if d.rule_id == "JUJU-003"]

    def test_range_pin_passes(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "requirements.txt").write_text("ops>=2.17,<4\n")
        report = lint(tmp_charm)
        assert not [d for d in report if d.rule_id in {"JUJU-003", "JUJU-004"}]

    def test_juju004_exact_pin_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "requirements.txt").write_text("ops==3.7.1\n")
        report = lint(tmp_charm)
        hits = [d for d in report if d.rule_id == "JUJU-004"]
        assert len(hits) == 1
        assert hits[0].severity == Severity.INFO
        assert hits[0].line == 1
        assert not [d for d in report if d.rule_id == "JUJU-003"]

    def test_requirements_line_number_is_reported(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "requirements.txt").write_text("# a comment\nrequests>=2.0\n\nops==3.7.1\n")
        report = lint(tmp_charm)
        hits = [d for d in report if d.rule_id == "JUJU-004"]
        assert len(hits) == 1
        assert hits[0].line == 4

    def test_juju004_exact_pin_in_pyproject_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "pyproject.toml").write_text('[project]\ndependencies = ["ops==3.7.1"]\n')
        report = lint(tmp_charm)
        assert [d for d in report if d.rule_id == "JUJU-004"]

    def test_no_ops_dependency_not_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "requirements.txt").write_text("requests>=2.0\n")
        report = lint(tmp_charm)
        assert not [d for d in report if d.rule_id in {"JUJU-003", "JUJU-004"}]

    def test_pyproject_ops_in_keywords_not_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "pyproject.toml").write_text(
            "[project]\n"
            'name = "ops"\n'
            'keywords = ["ops", "charm"]\n'
            'dependencies = ["ops>=2.17,<4"]\n'
        )
        report = lint(tmp_charm)
        assert not [d for d in report if d.rule_id in {"JUJU-003", "JUJU-004"}]

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
        assert [d for d in report if d.rule_id == "JUJU-004"]

    def test_pyproject_dependency_groups_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "pyproject.toml").write_text(
            '[project]\nname = "x"\n\n[dependency-groups]\ndev = ["ops"]\n'
        )
        report = lint(tmp_charm)
        assert [d for d in report if d.rule_id == "JUJU-003"]

    def test_poetry_caret_pin_not_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "pyproject.toml").write_text(
            "[tool.poetry]\n"
            'name = "x"\n'
            "\n"
            "[tool.poetry.dependencies]\n"
            'python = "^3.10"\n'
            'ops = "^2.17"\n'
        )
        report = lint(tmp_charm)
        assert not [d for d in report if d.rule_id in {"JUJU-003", "JUJU-004"}]

    def test_poetry_star_unpinned_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "pyproject.toml").write_text('[tool.poetry.dependencies]\nops = "*"\n')
        report = lint(tmp_charm)
        assert [d for d in report if d.rule_id == "JUJU-003"]

    def test_poetry_exact_pin_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "pyproject.toml").write_text('[tool.poetry.dependencies]\nops = "==3.7.1"\n')
        report = lint(tmp_charm)
        assert [d for d in report if d.rule_id == "JUJU-004"]

    def test_poetry_table_version_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "pyproject.toml").write_text(
            '[tool.poetry.dependencies]\nops = { version = "==3.7.1", extras = ["tracing"] }\n'
        )
        report = lint(tmp_charm)
        assert [d for d in report if d.rule_id == "JUJU-004"]

    def test_poetry_group_dependencies_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "pyproject.toml").write_text(
            '[tool.poetry.group.dev.dependencies]\nops = "==3.7.1"\n'
        )
        report = lint(tmp_charm)
        assert [d for d in report if d.rule_id == "JUJU-004"]

    def test_malformed_pyproject_does_not_crash(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "pyproject.toml").write_text("this is [not valid toml\n")
        (tmp_charm / "requirements.txt").write_text("ops==3.7.1\n")
        report = lint(tmp_charm)
        # falls through to requirements.txt
        assert [d for d in report if d.rule_id == "JUJU-004"]

    def test_uv_plugin_ignores_requirements_txt(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x", "parts": {"my-charm": {"plugin": "uv"}}})
        (tmp_charm / "requirements.txt").write_text("ops==3.7.1\n")
        report = lint(tmp_charm)
        assert not [d for d in report if d.rule_id in {"JUJU-003", "JUJU-004"}]

    def test_poetry_plugin_ignores_requirements_txt(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm, {"name": "x", "parts": {"my-charm": {"plugin": "poetry"}}}
        )
        (tmp_charm / "requirements.txt").write_text("ops\n")
        report = lint(tmp_charm)
        assert not [d for d in report if d.rule_id in {"JUJU-003", "JUJU-004"}]

    def test_uv_plugin_still_checks_pyproject(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x", "parts": {"my-charm": {"plugin": "uv"}}})
        (tmp_charm / "pyproject.toml").write_text(
            '[project]\nname = "x"\ndependencies = [\n  "ops==3.7.1",\n]\n'
        )
        report = lint(tmp_charm)
        assert [d for d in report if d.rule_id == "JUJU-004"]

    def test_charm_plugin_still_checks_requirements_txt(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x", "parts": {"my-charm": {"plugin": "charm"}}})
        (tmp_charm / "requirements.txt").write_text("ops==3.7.1\n")
        report = lint(tmp_charm)
        assert [d for d in report if d.rule_id == "JUJU-004"]
