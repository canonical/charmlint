"""Tests for STATUS-### rules."""

import pathlib
import textwrap

from charmlint._linter import lint
from charmlint._models import Severity
from tests.conftest import write_charm_source, write_charmcraft_yaml

RULE = "STATUS-001"


def _lint_source(charm_dir: pathlib.Path, source: str, filename: str = "charm.py"):
    """Lint a charm whose only content is *source*, returning STATUS-001 findings."""
    write_charmcraft_yaml(charm_dir, {"name": "test"})
    write_charm_source(charm_dir, textwrap.dedent(source), filename=filename)
    return [d for d in lint(charm_dir) if d.rule_id == RULE]


class TestBlockedStatusInNonRepeatingHandler:
    """STATUS-001 — BlockedStatus in an install/start/stop/remove handler."""

    def test_install_handler_flagged(self, tmp_charm: pathlib.Path):
        found = _lint_source(
            tmp_charm,
            """\
            import ops

            class C(ops.CharmBase):
                def __init__(self, framework):
                    super().__init__(framework)
                    framework.observe(self.on.install, self._on_install)

                def _on_install(self, event):
                    try:
                        install_workload()
                    except Exception:
                        self.unit.status = ops.BlockedStatus("install failed")
            """,
        )
        assert len(found) == 1
        assert found[0].severity == Severity.WARNING
        assert found[0].line == 12
        assert "_on_install" in found[0].message
        assert "install" in found[0].message

    def test_start_stop_remove_flagged(self, tmp_charm: pathlib.Path):
        found = _lint_source(
            tmp_charm,
            """\
            import ops
            from ops import BlockedStatus

            class C(ops.CharmBase):
                def __init__(self, framework):
                    super().__init__(framework)
                    framework.observe(self.on.start, self._on_start)
                    framework.observe(self.on.stop, self._on_stop)
                    framework.observe(self.on.remove, self._on_remove)

                def _on_start(self, event):
                    self.unit.status = BlockedStatus("nope")

                def _on_stop(self, event):
                    self.unit.status = BlockedStatus("nope")

                def _on_remove(self, event):
                    self.unit.status = BlockedStatus("nope")
            """,
        )
        assert len(found) == 3
        assert {"start", "stop", "remove"} == {d.message.split("'")[3] for d in found}

    def test_add_status_flagged(self, tmp_charm: pathlib.Path):
        found = _lint_source(
            tmp_charm,
            """\
            import ops

            class C(ops.CharmBase):
                def __init__(self, framework):
                    super().__init__(framework)
                    framework.observe(self.on.install, self._on_install)

                def _on_install(self, event):
                    event.add_status(ops.BlockedStatus("install failed"))
            """,
        )
        assert len(found) == 1
        assert found[0].line == 9

    def test_app_status_flagged(self, tmp_charm: pathlib.Path):
        found = _lint_source(
            tmp_charm,
            """\
            import ops
            from ops import BlockedStatus

            class C(ops.CharmBase):
                def __init__(self, framework):
                    super().__init__(framework)
                    framework.observe(self.on.install, self._on_install)

                def _on_install(self, event):
                    self.app.status = BlockedStatus("install failed")
            """,
        )
        assert len(found) == 1

    def test_self_framework_observe_recognised(self, tmp_charm: pathlib.Path):
        found = _lint_source(
            tmp_charm,
            """\
            import ops
            from ops import BlockedStatus

            class C(ops.CharmBase):
                def __init__(self, *args):
                    super().__init__(*args)
                    self.framework.observe(self.on.install, self._on_install)

                def _on_install(self, event):
                    self.unit.status = BlockedStatus("install failed")
            """,
        )
        assert len(found) == 1

    def test_every_offending_line_reported(self, tmp_charm: pathlib.Path):
        found = _lint_source(
            tmp_charm,
            """\
            import ops
            from ops import BlockedStatus

            class C(ops.CharmBase):
                def __init__(self, framework):
                    super().__init__(framework)
                    framework.observe(self.on.install, self._on_install)

                def _on_install(self, event):
                    if not self.config.get("port"):
                        self.unit.status = BlockedStatus("no port")
                    if not self.model.relations.get("db"):
                        self.unit.status = BlockedStatus("no db")
            """,
        )
        assert [d.line for d in found] == [11, 13]

    def test_other_status_types_not_flagged(self, tmp_charm: pathlib.Path):
        found = _lint_source(
            tmp_charm,
            """\
            import ops
            from ops import ActiveStatus, MaintenanceStatus, WaitingStatus

            class C(ops.CharmBase):
                def __init__(self, framework):
                    super().__init__(framework)
                    framework.observe(self.on.install, self._on_install)

                def _on_install(self, event):
                    self.unit.status = MaintenanceStatus("installing")
                    install_workload()
                    self.unit.status = ActiveStatus()
            """,
        )
        assert not found

    def test_repeating_event_not_flagged(self, tmp_charm: pathlib.Path):
        found = _lint_source(
            tmp_charm,
            """\
            import ops
            from ops import BlockedStatus

            class C(ops.CharmBase):
                def __init__(self, framework):
                    super().__init__(framework)
                    framework.observe(self.on.config_changed, self._on_config_changed)

                def _on_config_changed(self, event):
                    self.unit.status = BlockedStatus("bad config")
            """,
        )
        assert not found

    def test_handler_shared_with_repeating_event_not_flagged(self, tmp_charm: pathlib.Path):
        """A reconciler wired to install *and* config-changed still recovers."""
        found = _lint_source(
            tmp_charm,
            """\
            import ops
            from ops import BlockedStatus

            class C(ops.CharmBase):
                def __init__(self, framework):
                    super().__init__(framework)
                    framework.observe(self.on.install, self._reconcile)
                    framework.observe(self.on.config_changed, self._reconcile)

                def _reconcile(self, event):
                    self.unit.status = BlockedStatus("bad config")
            """,
        )
        assert not found

    def test_unnameable_event_expression_not_flagged(self, tmp_charm: pathlib.Path):
        """An observe call we can't resolve is assumed to be a recovering event."""
        found = _lint_source(
            tmp_charm,
            """\
            import ops
            from ops import BlockedStatus

            class C(ops.CharmBase):
                def __init__(self, framework):
                    super().__init__(framework)
                    framework.observe(self.on.install, self._reconcile)
                    framework.observe(self.database.on.ready, self._reconcile)

                def _reconcile(self, event):
                    self.unit.status = BlockedStatus("no db")
            """,
        )
        assert not found

    def test_unobserved_helper_not_flagged(self, tmp_charm: pathlib.Path):
        """Only the observed handler's own body is checked, not what it calls."""
        found = _lint_source(
            tmp_charm,
            """\
            import ops
            from ops import BlockedStatus

            class C(ops.CharmBase):
                def __init__(self, framework):
                    super().__init__(framework)
                    framework.observe(self.on.install, self._on_install)

                def _on_install(self, event):
                    self._reconcile()

                def _reconcile(self):
                    self.unit.status = BlockedStatus("no db")
            """,
        )
        assert not found

    def test_local_variable_assignment_not_flagged(self, tmp_charm: pathlib.Path):
        found = _lint_source(
            tmp_charm,
            """\
            import ops
            from ops import BlockedStatus

            class C(ops.CharmBase):
                def __init__(self, framework):
                    super().__init__(framework)
                    framework.observe(self.on.install, self._on_install)

                def _on_install(self, event):
                    fallback = BlockedStatus("unused")
            """,
        )
        assert not found

    def test_vendored_library_skipped(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        lib_dir = tmp_charm / "lib" / "charms" / "other" / "v0"
        lib_dir.mkdir(parents=True)
        (lib_dir / "thing.py").write_text(
            textwrap.dedent("""\
                import ops
                from ops import BlockedStatus

                class C(ops.Object):
                    def __init__(self, charm):
                        charm.framework.observe(charm.on.install, self._on_install)

                    def _on_install(self, event):
                        self.unit.status = BlockedStatus("install failed")
            """)
        )
        assert not [d for d in lint(tmp_charm) if d.rule_id == RULE]

    def test_syntax_error_ignored(self, tmp_charm: pathlib.Path):
        found = _lint_source(tmp_charm, "def broken(:\n")
        assert not found

    def test_diagnostic_metadata(self, tmp_charm: pathlib.Path):
        found = _lint_source(
            tmp_charm,
            """\
            import ops
            from ops import BlockedStatus

            class C(ops.CharmBase):
                def __init__(self, framework):
                    super().__init__(framework)
                    framework.observe(self.on.install, self._on_install)

                def _on_install(self, event):
                    self.unit.status = BlockedStatus("install failed")
            """,
        )
        assert len(found) == 1
        assert found[0].path == str(tmp_charm.resolve() / "src" / "charm.py")
        assert found[0].fix_hint is not None
        assert found[0].reference_url is not None
