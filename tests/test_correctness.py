"""Tests for correctness rules."""

import pathlib
import textwrap

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

    def test_syntax_error_ignored(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(tmp_charm, "def broken(:\n")
        report = lint(tmp_charm)
        assert not [d for d in report if d.rule_id == RULE_ID]

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
