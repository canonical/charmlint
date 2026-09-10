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
        # A following raise is not acceptable - it just belongs to
        # CORRECTNESS-002, so CORRECTNESS-001 stays silent to avoid a
        # duplicate diagnostic on the same line.
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

    def test_defer_in_if_with_stmt_after_block_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        write_charm_source(
            tmp_charm,
            "def handler(self, event):\n"
            "    if not self.ready:\n"
            "        event.defer()\n"
            "    self.do_more_work()\n",
        )
        report = lint(tmp_charm)
        hits = [d for d in list(report) if d.rule_id == "CORRECTNESS-001"]
        assert len(hits) == 1

    def test_defer_last_in_nested_function_not_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        write_charm_source(
            tmp_charm,
            "def handler(self, event):\n    def inner():\n        event.defer()\n    inner()\n",
        )
        report = lint(tmp_charm)
        assert not [d for d in list(report) if d.rule_id == "CORRECTNESS-001"]

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

    def test_defer_in_if_with_raise_after_block_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        write_charm_source(
            tmp_charm,
            "def handler(self, event):\n"
            "    if not self.ready:\n"
            "        event.defer()\n"
            "    raise RuntimeError('nope')\n",
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

    def test_src_lib_directory_is_checked(self, tmp_charm: pathlib.Path):
        # Only the top-level lib/ is fetch-lib output; src/lib/ is the charm's own code.
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        src_lib = tmp_charm / "src" / "lib"
        src_lib.mkdir(parents=True)
        (src_lib / "helper.py").write_text(
            "def handler(self, event):\n    event.defer()\n    raise RuntimeError('x')\n",
        )
        report = lint(tmp_charm)
        assert len([d for d in list(report) if d.rule_id == "CORRECTNESS-002"]) == 1


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
