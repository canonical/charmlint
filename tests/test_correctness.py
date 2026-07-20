"""Tests for correctness rules."""

import pathlib

from charmlint._linter import lint
from charmlint._models import Severity
from tests.conftest import write_charm_source, write_charmcraft_yaml


class TestDeferWithoutReturn:
    """Tests for CORRECTNESS-001 — event.defer() without a following return."""

    def test_defer_then_other_stmt_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        write_charm_source(
            tmp_charm,
            "def handler(self, event):\n    event.defer()\n    self.do_more_work()\n",
        )
        report = lint(tmp_charm)
        hits = [d for d in list(report) if d.rule_id == "CORRECTNESS-001"]
        assert len(hits) == 1
        assert hits[0].severity == Severity.WARNING

    def test_defer_then_return_not_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        write_charm_source(
            tmp_charm,
            "def handler(self, event):\n    event.defer()\n    return\n",
        )
        report = lint(tmp_charm)
        assert not [d for d in list(report) if d.rule_id == "CORRECTNESS-001"]

    def test_defer_then_raise_not_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        write_charm_source(
            tmp_charm,
            "def handler(self, event):\n    event.defer()\n    raise RuntimeError('x')\n",
        )
        report = lint(tmp_charm)
        assert not [d for d in list(report) if d.rule_id == "CORRECTNESS-001"]

    def test_defer_last_statement_not_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        write_charm_source(
            tmp_charm,
            "def handler(self, event):\n    self.prepare()\n    event.defer()\n",
        )
        report = lint(tmp_charm)
        assert not [d for d in list(report) if d.rule_id == "CORRECTNESS-001"]

    def test_defer_last_in_if_block_not_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        write_charm_source(
            tmp_charm,
            "def handler(self, event):\n    if not self.ready:\n        event.defer()\n",
        )
        report = lint(tmp_charm)
        assert not [d for d in list(report) if d.rule_id == "CORRECTNESS-001"]

    def test_defer_inside_if_with_trailing_stmt_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        write_charm_source(
            tmp_charm,
            "def handler(self, event):\n"
            "    if not self.ready:\n"
            "        event.defer()\n"
            "        self.cleanup()\n",
        )
        report = lint(tmp_charm)
        hits = [d for d in list(report) if d.rule_id == "CORRECTNESS-001"]
        assert len(hits) == 1

    def test_ignores_lib_directory(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        lib = tmp_charm / "lib" / "charms" / "other" / "v0"
        lib.mkdir(parents=True)
        (lib / "thing.py").write_text(
            "def handler(self, event):\n    event.defer()\n    self.do_more_work()\n",
        )
        report = lint(tmp_charm)
        assert not [d for d in list(report) if d.rule_id == "CORRECTNESS-001"]


class TestDeferBeforeRaise:
    """Tests for CORRECTNESS-002 — event.defer() followed by raise."""

    def test_defer_then_raise_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        write_charm_source(
            tmp_charm,
            "def handler(self, event):\n    event.defer()\n    raise RuntimeError('x')\n",
        )
        report = lint(tmp_charm)
        hits = [d for d in list(report) if d.rule_id == "CORRECTNESS-002"]
        assert len(hits) == 1
        assert hits[0].severity == Severity.WARNING

    def test_defer_then_raise_in_if_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        write_charm_source(
            tmp_charm,
            "def handler(self, event):\n"
            "    if not self.ready:\n"
            "        event.defer()\n"
            "        raise RuntimeError('nope')\n",
        )
        report = lint(tmp_charm)
        hits = [d for d in list(report) if d.rule_id == "CORRECTNESS-002"]
        assert len(hits) == 1

    def test_defer_then_return_not_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        write_charm_source(
            tmp_charm,
            "def handler(self, event):\n    event.defer()\n    return\n",
        )
        report = lint(tmp_charm)
        assert not [d for d in list(report) if d.rule_id == "CORRECTNESS-002"]

    def test_defer_last_statement_not_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        write_charm_source(
            tmp_charm,
            "def handler(self, event):\n    self.prepare()\n    event.defer()\n",
        )
        report = lint(tmp_charm)
        assert not [d for d in list(report) if d.rule_id == "CORRECTNESS-002"]

    def test_ignores_lib_directory(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        lib = tmp_charm / "lib" / "charms" / "other" / "v0"
        lib.mkdir(parents=True)
        (lib / "thing.py").write_text(
            "def handler(self, event):\n    event.defer()\n    raise RuntimeError('x')\n",
        )
        report = lint(tmp_charm)
        assert not [d for d in list(report) if d.rule_id == "CORRECTNESS-002"]
