"""Tests for the CORRECTNESS rules."""

import pathlib

from charmlint._linter import lint
from charmlint._models import Severity
from tests.conftest import write_charm_source, write_charmcraft_yaml


class TestExecResultNotConsumed:
    """CORRECTNESS-003 — bare container.exec() result not consumed."""

    def test_bare_exec_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        write_charm_source(tmp_charm, "def f(container):\n    container.exec(['echo', 'hi'])\n")
        report = lint(tmp_charm)
        hits = [d for d in report if d.rule_id == "CORRECTNESS-003"]
        assert len(hits) == 1
        assert hits[0].severity == Severity.ERROR
        assert hits[0].line == 2

    def test_self_container_attr_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        write_charm_source(tmp_charm, "def f(self):\n    self._container.exec(['echo', 'hi'])\n")
        report = lint(tmp_charm)
        hits = [d for d in report if d.rule_id == "CORRECTNESS-003"]
        assert len(hits) == 1
        assert hits[0].line == 2

    def test_chained_wait_not_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        write_charm_source(
            tmp_charm, "def f(container):\n    container.exec(['echo', 'hi']).wait()\n"
        )
        report = lint(tmp_charm)
        assert not [d for d in report if d.rule_id == "CORRECTNESS-003"]

    def test_chained_wait_output_not_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        write_charm_source(
            tmp_charm, "def f(container):\n    container.exec(['echo', 'hi']).wait_output()\n"
        )
        report = lint(tmp_charm)
        assert not [d for d in report if d.rule_id == "CORRECTNESS-003"]

    def test_result_captured_not_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        write_charm_source(
            tmp_charm,
            "def f(container):\n    result = container.exec(['echo', 'hi'])\n    result.wait()\n",
        )
        report = lint(tmp_charm)
        assert not [d for d in report if d.rule_id == "CORRECTNESS-003"]

    def test_workload_wrapper_not_flagged(self, tmp_charm: pathlib.Path):
        # A blocking ``WorkloadBase.exec()`` wrapper (returns a str) is not the
        # Pebble API, so discarding its result is correct and must not be flagged.
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        write_charm_source(tmp_charm, "def f(self):\n    self.workload.exec(['echo', 'hi'])\n")
        report = lint(tmp_charm)
        assert not [d for d in report if d.rule_id == "CORRECTNESS-003"]

    def test_self_exec_not_flagged(self, tmp_charm: pathlib.Path):
        # ``self.exec(...)`` inside a WorkloadBase subclass is the same wrapper.
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        write_charm_source(tmp_charm, "def f(self):\n    self.exec(['echo', 'hi'])\n")
        report = lint(tmp_charm)
        assert not [d for d in report if d.rule_id == "CORRECTNESS-003"]

    def test_ignores_lib_directory(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        lib = tmp_charm / "lib" / "charms" / "other" / "v0"
        lib.mkdir(parents=True)
        (lib / "thing.py").write_text("def f(container):\n    container.exec(['echo'])\n")
        report = lint(tmp_charm)
        assert not [d for d in report if d.rule_id == "CORRECTNESS-003"]
