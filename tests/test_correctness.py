"""Tests for correctness rules."""

import pathlib
import textwrap
from typing import Any

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
        assert (hits[0].path, hits[0].line) == ("src/charm.py", 2)

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
        assert (hits[0].path, hits[0].line) == ("src/charm.py", 2)

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


RULE_ID = "CORRECTNESS-004"


def _charm(body: str) -> str:
    """Wrap handler/observe lines in a minimal charm class."""
    return textwrap.dedent(body)


class TestNonDeferrableEventDeferred:
    """CORRECTNESS-004 — event.defer() in a handler for a non-deferrable event."""

    def test_defer_in_stop_handler_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            _charm("""\
                import ops

                class C(ops.CharmBase):
                    def __init__(self, framework):
                        super().__init__(framework)
                        framework.observe(self.on.stop, self._on_stop)

                    def _on_stop(self, event):
                        event.defer()
            """),
        )
        report = lint(tmp_charm)
        hits = [d for d in report if d.rule_id == RULE_ID]
        assert len(hits) == 1
        assert hits[0].severity == Severity.ERROR
        assert "'stop'" in hits[0].message
        assert hits[0].line == 9

    def test_defer_in_action_handler_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            _charm("""\
                import ops

                class C(ops.CharmBase):
                    def __init__(self, framework):
                        super().__init__(framework)
                        framework.observe(self.on.pause_action, self._on_pause)

                    def _on_pause(self, event):
                        if not self.ready:
                            event.defer()
            """),
        )
        report = lint(tmp_charm)
        hits = [d for d in report if d.rule_id == RULE_ID]
        assert len(hits) == 1
        assert "'pause-action'" in hits[0].message

    def test_subscript_action_form_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            _charm("""\
                import ops

                class C(ops.CharmBase):
                    def __init__(self, framework):
                        super().__init__(framework)
                        framework.observe(self.on['do-thing'].action, self._on_do_thing)

                    def _on_do_thing(self, event):
                        event.defer()
            """),
        )
        report = lint(tmp_charm)
        hits = [d for d in report if d.rule_id == RULE_ID]
        assert len(hits) == 1
        assert "'do-thing-action'" in hits[0].message

    def test_secret_rotate_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            _charm("""\
                import ops

                class C(ops.CharmBase):
                    def __init__(self, framework):
                        super().__init__(framework)
                        framework.observe(self.on.secret_rotate, self._on_rotate)

                    def _on_rotate(self, event):
                        event.defer()
            """),
        )
        report = lint(tmp_charm)
        hits = [d for d in report if d.rule_id == RULE_ID]
        assert len(hits) == 1
        assert "'secret-rotate'" in hits[0].message

    def test_collect_status_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            _charm("""\
                import ops

                class C(ops.CharmBase):
                    def __init__(self, framework):
                        super().__init__(framework)
                        framework.observe(self.on.collect_unit_status, self._on_collect)

                    def _on_collect(self, event):
                        event.defer()
            """),
        )
        report = lint(tmp_charm)
        hits = [d for d in report if d.rule_id == RULE_ID]
        assert len(hits) == 1
        assert "'collect-unit-status'" in hits[0].message

    def test_defer_in_nested_function_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            _charm("""\
                import ops

                class C(ops.CharmBase):
                    def __init__(self, framework):
                        super().__init__(framework)
                        framework.observe(self.on.remove, self._on_remove)

                    def _on_remove(self, event):
                        def retry():
                            event.defer()

                        retry()
            """),
        )
        report = lint(tmp_charm)
        hits = [d for d in report if d.rule_id == RULE_ID]
        assert len(hits) == 1
        assert "'remove'" in hits[0].message

    def test_multiple_defers_all_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            _charm("""\
                import ops

                class C(ops.CharmBase):
                    def __init__(self, framework):
                        super().__init__(framework)
                        framework.observe(self.on.stop, self._on_stop)

                    def _on_stop(self, event):
                        if self.a:
                            event.defer()
                        if self.b:
                            event.defer()
            """),
        )
        report = lint(tmp_charm)
        assert len([d for d in report if d.rule_id == RULE_ID]) == 2

    def test_deferrable_event_not_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            _charm("""\
                import ops

                class C(ops.CharmBase):
                    def __init__(self, framework):
                        super().__init__(framework)
                        framework.observe(self.on.config_changed, self._on_config_changed)

                    def _on_config_changed(self, event):
                        event.defer()
            """),
        )
        report = lint(tmp_charm)
        assert not [d for d in report if d.rule_id == RULE_ID]

    def test_handler_without_defer_not_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            _charm("""\
                import ops

                class C(ops.CharmBase):
                    def __init__(self, framework):
                        super().__init__(framework)
                        framework.observe(self.on.stop, self._on_stop)

                    def _on_stop(self, event):
                        self.workload.stop()
            """),
        )
        report = lint(tmp_charm)
        assert not [d for d in report if d.rule_id == RULE_ID]

    def test_defer_on_other_object_not_flagged(self, tmp_charm: pathlib.Path):
        # Deferring some *other* event stashed on the charm is not this bug.
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            _charm("""\
                import ops

                class C(ops.CharmBase):
                    def __init__(self, framework):
                        super().__init__(framework)
                        framework.observe(self.on.stop, self._on_stop)

                    def _on_stop(self, event):
                        self._pending_event.defer()
            """),
        )
        report = lint(tmp_charm)
        assert not [d for d in report if d.rule_id == RULE_ID]

    def test_custom_library_event_not_flagged(self, tmp_charm: pathlib.Path):
        # A custom event named `commit` on a library object is not the
        # framework's non-deferrable `commit` lifecycle event, but the rule
        # can't tell them apart from `self.on.commit`; only `self.on.<event>`
        # and `self.<lib>.on.<event>` are matched, so document the behaviour.
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            _charm("""\
                import ops

                class C(ops.CharmBase):
                    def __init__(self, framework):
                        super().__init__(framework)
                        framework.observe(self.db.on.database_created, self._on_db)

                    def _on_db(self, event):
                        event.defer()
            """),
        )
        report = lint(tmp_charm)
        assert not [d for d in report if d.rule_id == RULE_ID]

    def test_non_self_handler_not_flagged(self, tmp_charm: pathlib.Path):
        # A module-level handler isn't `self.<handler>`, so the handler map
        # can't be built for it and nothing is reported.
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            _charm("""\
                import ops

                def on_stop(event):
                    event.defer()

                class C(ops.CharmBase):
                    def __init__(self, framework):
                        super().__init__(framework)
                        framework.observe(self.on.stop, on_stop)
            """),
        )
        report = lint(tmp_charm)
        assert not [d for d in report if d.rule_id == RULE_ID]

    def test_non_literal_action_key_not_flagged(self, tmp_charm: pathlib.Path):
        # `self.on[NAME].action` hides the action name behind a constant.
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            _charm("""\
                import ops

                ACTION = 'do-thing'

                class C(ops.CharmBase):
                    def __init__(self, framework):
                        super().__init__(framework)
                        framework.observe(self.on[ACTION].action, self._on_do_thing)

                    def _on_do_thing(self, event):
                        event.defer()
            """),
        )
        report = lint(tmp_charm)
        assert not [d for d in report if d.rule_id == RULE_ID]

    def test_non_event_first_argument_not_flagged(self, tmp_charm: pathlib.Path):
        # `observe()` on something that isn't a bound-event expression at all.
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            _charm("""\
                import ops

                class C(ops.CharmBase):
                    def __init__(self, framework):
                        super().__init__(framework)
                        framework.observe(self.events['stop'].bound, self._on_stop)
                        framework.observe(self.stop_event, self._on_stop)

                    def _on_stop(self, event):
                        event.defer()
            """),
        )
        report = lint(tmp_charm)
        assert not [d for d in report if d.rule_id == RULE_ID]

    def test_handler_without_event_parameter_not_flagged(self, tmp_charm: pathlib.Path):
        # No event parameter to defer — whatever `event` names here, it isn't
        # the dispatched event.
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            _charm("""\
                import ops

                class C(ops.CharmBase):
                    def __init__(self, framework):
                        super().__init__(framework)
                        framework.observe(self.on.stop, self._on_stop)

                    def _on_stop(self):
                        event = self._pending
                        event.defer()
            """),
        )
        report = lint(tmp_charm)
        assert not [d for d in report if d.rule_id == RULE_ID]

    def test_ignores_lib_directory(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        lib_dir = tmp_charm / "lib" / "charms" / "other" / "v0"
        lib_dir.mkdir(parents=True)
        (lib_dir / "thing.py").write_text(
            _charm("""\
                import ops

                class C(ops.Object):
                    def __init__(self, framework):
                        super().__init__(framework, 'x')
                        framework.observe(self.on.stop, self._on_stop)

                    def _on_stop(self, event):
                        event.defer()
            """),
        )
        report = lint(tmp_charm)
        assert not [d for d in report if d.rule_id == RULE_ID]

    def test_syntax_error_is_fatal(self, tmp_charm: pathlib.Path):
        """A source that does not parse is reported by the core, not skipped here."""
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(tmp_charm, "def broken(:\n")
        assert [d.rule_id for d in lint(tmp_charm)] == ["FATAL"]

    def test_diagnostic_has_reference_url(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            _charm("""\
                import ops

                class C(ops.CharmBase):
                    def __init__(self, framework):
                        super().__init__(framework)
                        framework.observe(self.on.stop, self._on_stop)

                    def _on_stop(self, event):
                        event.defer()
            """),
        )
        report = lint(tmp_charm)
        hits = [d for d in report if d.rule_id == RULE_ID]
        assert hits[0].reference_url is not None
        assert "defer-guidance" in hits[0].reference_url


_RULE = "CORRECTNESS-008"


def _lint_source(charm_dir: pathlib.Path, source: str, **metadata: Any):
    """Lint a charm with the given src/charm.py, returning CORRECTNESS-008 findings."""
    write_charmcraft_yaml(charm_dir, {"name": "test", **metadata})
    write_charm_source(charm_dir, textwrap.dedent(source))
    return [d for d in lint(charm_dir) if d.rule_id == _RULE]


def _charm_class(body: str) -> str:
    """A charm class whose ``__init__`` and methods are *body*."""
    return "import ops\n\nclass MyCharm(ops.CharmBase):\n" + textwrap.indent(
        textwrap.dedent(body), "    "
    )


class TestObserveTargetMismatch:
    """CORRECTNESS-008 — observe() must name a real event and a real handler."""

    def test_missing_handler_is_error(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _charm_class("""
                def __init__(self, framework):
                    super().__init__(framework)
                    framework.observe(self.on.start, self._on_start)
            """),
        )
        assert len(findings) == 1
        assert findings[0].severity == Severity.ERROR
        assert "_on_start" in findings[0].message
        assert "MyCharm" in findings[0].message
        assert findings[0].path == "src/charm.py"
        assert findings[0].line is not None

    def test_defined_handler_is_clean(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _charm_class("""
                def __init__(self, framework):
                    super().__init__(framework)
                    framework.observe(self.on.start, self._on_start)

                def _on_start(self, event):
                    pass
            """),
        )
        assert not findings

    def test_handler_assigned_in_init_is_clean(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _charm_class("""
                def __init__(self, framework):
                    super().__init__(framework)
                    self._on_start = lambda event: None
                    framework.observe(self.on.start, self._on_start)
            """),
        )
        assert not findings

    def test_handler_on_another_object_is_ignored(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _charm_class("""
                def __init__(self, framework):
                    super().__init__(framework)
                    framework.observe(self.on.start, self.helper.on_start)
            """),
        )
        assert not findings

    def test_setattr_silences_the_handler_check(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _charm_class("""
                def __init__(self, framework):
                    super().__init__(framework)
                    setattr(self, "_on_start", lambda event: None)
                    framework.observe(self.on.start, self._on_start)
            """),
        )
        assert not findings

    def test_getattr_silences_the_handler_check(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _charm_class("""
                def __init__(self, framework):
                    super().__init__(framework)
                    framework.observe(self.on.start, self._on_start)

                def __getattr__(self, name):
                    return lambda event: None
            """),
        )
        assert not findings

    def test_intermediate_base_class_is_skipped(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            """
            import ops
            from somewhere import SharedBase

            class MyCharm(SharedBase):
                def __init__(self, framework):
                    super().__init__(framework)
                    framework.observe(self.on.start, self._on_start)
            """,
        )
        assert not findings

    def test_undeclared_relation_event_is_error(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _charm_class("""
                def __init__(self, framework):
                    super().__init__(framework)
                    framework.observe(self.on.db_relation_changed, self._on_db)

                def _on_db(self, event):
                    pass
            """),
            requires={"database": {"interface": "db"}},
        )
        assert len(findings) == 1
        assert findings[0].severity == Severity.ERROR
        assert "db_relation_changed" in findings[0].message
        assert findings[0].fix_hint is not None
        assert "provides:" in findings[0].fix_hint

    def test_declared_relation_event_is_clean(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _charm_class("""
                def __init__(self, framework):
                    super().__init__(framework)
                    framework.observe(self.on.database_relation_changed, self._on_db)
                    framework.observe(self.on.peers_relation_departed, self._on_db)
                    framework.observe(self.on.web_ui_relation_broken, self._on_db)

                def _on_db(self, event):
                    pass
            """),
            requires={"database": {"interface": "db"}},
            provides={"web-ui": {"interface": "http"}},
            peers={"peers": {"interface": "peers"}},
        )
        assert not findings

    def test_declared_container_storage_and_action_events_are_clean(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _charm_class("""
                def __init__(self, framework):
                    super().__init__(framework)
                    framework.observe(self.on.web_pebble_ready, self._handle)
                    framework.observe(self.on.web_pebble_check_failed, self._handle)
                    framework.observe(self.on.data_storage_attached, self._handle)
                    framework.observe(self.on.do_thing_action, self._handle)

                def _handle(self, event):
                    pass
            """),
            containers={"web": {"resource": "image"}},
            storage={"data": {"type": "filesystem"}},
            actions={"do-thing": {"description": "x"}},
        )
        assert not findings

    def test_undeclared_container_event_names_the_container(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _charm_class("""
                def __init__(self, framework):
                    super().__init__(framework)
                    framework.observe(self.on.workload_pebble_ready, self._handle)

                def _handle(self, event):
                    pass
            """),
            containers={"web": {"resource": "image"}},
        )
        assert len(findings) == 1
        assert findings[0].fix_hint is not None
        assert "'workload'" in findings[0].fix_hint
        assert "containers:" in findings[0].fix_hint

    def test_lifecycle_events_are_clean(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _charm_class("""
                def __init__(self, framework):
                    super().__init__(framework)
                    framework.observe(self.on.install, self._handle)
                    framework.observe(self.on.collect_unit_status, self._handle)
                    framework.observe(self.on.secret_rotate, self._handle)

                def _handle(self, event):
                    pass
            """),
        )
        assert not findings

    def test_subscript_form_resolves_the_endpoint(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _charm_class("""
                def __init__(self, framework):
                    super().__init__(framework)
                    framework.observe(self.on["web-ui"].relation_changed, self._handle)
                    framework.observe(self.on["missing"].relation_changed, self._handle)

                def _handle(self, event):
                    pass
            """),
            provides={"web-ui": {"interface": "http"}},
        )
        assert len(findings) == 1
        assert "missing_relation_changed" in findings[0].message

    def test_library_event_source_is_not_checked(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _charm_class("""
                def __init__(self, framework):
                    super().__init__(framework)
                    self.database = DatabaseRequires(self)
                    framework.observe(self.database.on.database_created, self._handle)

                def _handle(self, event):
                    pass
            """),
        )
        assert not findings

    def test_custom_charm_events_are_recognised(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            """
            import ops

            class MyCharmEvents(ops.CharmEvents):
                thing_happened = ops.EventSource(ops.EventBase)

            class MyCharm(ops.CharmBase):
                on = MyCharmEvents()

                def __init__(self, framework):
                    super().__init__(framework)
                    framework.observe(self.on.thing_happened, self._handle)

                def _handle(self, event):
                    pass
            """,
        )
        assert not findings

    def test_unresolvable_custom_events_silence_the_event_check(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            """
            import ops
            from somewhere import LibraryEvents

            class MyCharm(ops.CharmBase):
                on = LibraryEvents()

                def __init__(self, framework):
                    super().__init__(framework)
                    framework.observe(self.on.thing_happened, self._handle)

                def _handle(self, event):
                    pass
            """,
        )
        assert not findings

    def test_dynamic_define_event_silences_the_event_check(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _charm_class("""
                def __init__(self, framework):
                    super().__init__(framework)
                    for name in ("a", "b"):
                        self.on.define_event(name, ops.EventBase)
                    framework.observe(self.on.thing_happened, self._handle)

                def _handle(self, event):
                    pass
            """),
        )
        assert not findings

    def test_dynamic_define_event_still_checks_handlers(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _charm_class("""
                def __init__(self, framework):
                    super().__init__(framework)
                    for name in ("a", "b"):
                        self.on.define_event(name, ops.EventBase)
                    framework.observe(self.on.start, self._on_start)
            """),
        )
        assert len(findings) == 1
        assert "_on_start" in findings[0].message

    def test_class_body_import_binds_a_handler(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _charm_class("""
                from actions.enable import on_enable_action

                def __init__(self, framework):
                    super().__init__(framework)
                    framework.observe(self.on.enable_action, self.on_enable_action)
            """),
            actions={"enable": {"description": "x"}},
        )
        assert not findings

    def test_literal_define_event_is_recognised(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _charm_class("""
                def __init__(self, framework):
                    super().__init__(framework)
                    self.on.define_event("thing_happened", ops.EventBase)
                    framework.observe(self.on.thing_happened, self._handle)

                def _handle(self, event):
                    pass
            """),
        )
        assert not findings

    def test_dynamic_event_reference_is_ignored(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _charm_class("""
                def __init__(self, framework):
                    super().__init__(framework)
                    framework.observe(self.on[EVENT].relation_changed, self._handle)

                def _handle(self, event):
                    pass
            """),
        )
        assert not findings

    def test_both_halves_reported_when_both_are_broken(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _charm_class("""
                def __init__(self, framework):
                    super().__init__(framework)
                    framework.observe(self.on.nope_relation_changed, self._on_nope)
            """),
        )
        assert len(findings) == 2
        assert "nope_relation_changed" in findings[0].message
        assert "_on_nope" in findings[1].message
        assert findings[0].line == findings[1].line

    def test_charm_without_metadata_is_not_reported(self, tmp_charm: pathlib.Path):
        write_charm_source(
            tmp_charm,
            textwrap.dedent(
                _charm_class("""
                    def __init__(self, framework):
                        super().__init__(framework)
                        framework.observe(self.on.db_relation_changed, self._handle)

                    def _handle(self, event):
                        pass
                """)
            ),
        )
        findings = [d for d in lint(tmp_charm) if d.rule_id == _RULE]
        assert not findings


_CONTAINER_RULE = "CORRECTNESS-009"
_CONTAINERS = {"containers": {"workload": {"resource": "workload-image"}}}


def _lint_container_charm(charm_dir: pathlib.Path, source: str, **metadata: Any):
    """Lint a charm with the given src/charm.py, returning CORRECTNESS-009 findings."""
    write_charmcraft_yaml(charm_dir, {"name": "test", **metadata})
    write_charm_source(charm_dir, textwrap.dedent(source))
    return [d for d in lint(charm_dir) if d.rule_id == _CONTAINER_RULE]


def _container_charm(body: str) -> str:
    """A charm whose ``_reconcile`` body is *body*."""
    return "import ops\n\nclass C(ops.CharmBase):\n    def _reconcile(self):\n" + textwrap.indent(
        textwrap.dedent(body), " " * 8
    )


class TestContainerNameMismatch:
    """CORRECTNESS-009 — get_container() must name a declared container."""

    def test_declared_name_not_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_container_charm(
            tmp_charm, _container_charm('self.unit.get_container("workload")'), **_CONTAINERS
        )
        assert not findings

    def test_undeclared_name_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_container_charm(
            tmp_charm, _container_charm('self.unit.get_container("test")'), **_CONTAINERS
        )
        assert len(findings) == 1
        assert findings[0].severity == Severity.ERROR
        assert "'test'" in findings[0].message
        assert "'workload'" in findings[0].message
        assert findings[0].path == "src/charm.py"
        assert findings[0].line == 5

    def test_keyword_argument_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_container_charm(
            tmp_charm,
            _container_charm('self.unit.get_container(container_name="test")'),
            **_CONTAINERS,
        )
        assert len(findings) == 1

    def test_no_containers_declared_ignored(self, tmp_charm: pathlib.Path):
        """A charm declaring no containers builds them somewhere charmlint can't see."""
        findings = _lint_container_charm(
            tmp_charm, _container_charm('self.unit.get_container("workload")')
        )
        assert not findings

    def test_charmcraft_extension_ignored(self, tmp_charm: pathlib.Path):
        """An extension injects containers that never appear in charmcraft.yaml."""
        findings = _lint_container_charm(
            tmp_charm,
            _container_charm('self.unit.get_container("app")'),
            extensions=["go-framework"],
            **_CONTAINERS,
        )
        assert not findings

    def test_every_call_reported(self, tmp_charm: pathlib.Path):
        findings = _lint_container_charm(
            tmp_charm,
            _container_charm("""\
                self.unit.get_container("one")
                self.model.unit.get_container("two")
            """),
            **_CONTAINERS,
        )
        assert len(findings) == 2
        assert [f.line for f in findings] == [5, 6]

    def test_non_literal_name_ignored(self, tmp_charm: pathlib.Path):
        findings = _lint_container_charm(
            tmp_charm,
            _container_charm("""\
                for name in self.meta.containers:
                    self.unit.get_container(name)
                self.unit.get_container(f"{self.app.name}-workload")
                self.unit.get_container(self.config["container"])
            """),
            **_CONTAINERS,
        )
        assert not findings

    def test_unrelated_calls_ignored(self, tmp_charm: pathlib.Path):
        findings = _lint_container_charm(
            tmp_charm,
            _container_charm("""\
                self.unit.get_container()
                helper("nginx")
            """),
            **_CONTAINERS,
        )
        assert not findings

    def test_no_metadata_is_fatal_not_a_finding(self, tmp_charm: pathlib.Path):
        """A directory with no metadata at all is not a charm to report on."""
        write_charm_source(tmp_charm, _container_charm('self.unit.get_container("workload")'))
        assert not [d for d in lint(tmp_charm) if d.rule_id == _CONTAINER_RULE]

    def test_owned_library_ignored(self, tmp_charm: pathlib.Path):
        """A library this charm publishes runs inside other charms."""
        write_charmcraft_yaml(tmp_charm, {"name": "test", **_CONTAINERS})
        lib = tmp_charm / "lib" / "charms" / "test" / "v0"
        lib.mkdir(parents=True)
        (lib / "helper.py").write_text('def f(unit):\n    unit.get_container("other")\n')
        write_charm_source(tmp_charm, "import ops\n")
        assert not [d for d in lint(tmp_charm) if d.rule_id == _CONTAINER_RULE]

    def test_tests_ignored(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test", **_CONTAINERS})
        write_charm_source(tmp_charm, "import ops\n")
        unit = tmp_charm / "tests" / "unit"
        unit.mkdir(parents=True)
        (unit / "test_charm.py").write_text('def test_x(unit):\n    unit.get_container("other")\n')
        assert not [d for d in lint(tmp_charm) if d.rule_id == _CONTAINER_RULE]
