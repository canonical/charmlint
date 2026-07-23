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
        assert not [d for d in report if d.rule_id == "JUJU-003"]

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
