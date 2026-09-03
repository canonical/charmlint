"""Tests for FEATURES-### rules."""

import pathlib
import textwrap

from charmlint._linter import lint
from charmlint._models import Severity
from tests.conftest import write_charm_source, write_charmcraft_yaml

_OPTIONS = {"config": {"options": {"port": {"type": "int", "description": "HTTP port"}}}}


def _lint_source(charm_dir: pathlib.Path, source: str, *, options: bool = True):
    """Lint a charm whose ``src/charm.py`` is *source*, returning FEATURES-006 findings."""
    metadata: dict[str, object] = {"name": "test"}
    if options:
        metadata.update(_OPTIONS)
    write_charmcraft_yaml(charm_dir, metadata)
    write_charm_source(charm_dir, textwrap.dedent(source))
    return [d for d in lint(charm_dir) if d.rule_id == "FEATURES-006"]


def _charm(init: str, *, body: str = "", reads_config: bool = True) -> str:
    """A charm source whose ``__init__`` body is *init*.

    *init* and *body* are written without indentation and indented here to
    the depth the class needs.
    """
    read = "        print(self.config['port'])\n" if reads_config else ""
    return (
        "import ops\n\n\n"
        "class TestCharm(ops.CharmBase):\n"
        "    def __init__(self, framework):\n"
        "        super().__init__(framework)\n"
        + textwrap.indent(textwrap.dedent(init), " " * 8)
        + "\n    def _handler(self, event):\n"
        + (read or "        pass\n")
        + textwrap.indent(textwrap.dedent(body), " " * 4)
        + "\n\nops.main(TestCharm)\n"
    )


class TestNoConfigChangedObserver:
    """FEATURES-006 — declared config options with nothing handling a change."""

    def test_options_without_observer_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm, _charm("framework.observe(self.on.start, self._handler)")
        )
        assert len(findings) == 1
        assert findings[0].severity == Severity.WARNING
        assert findings[0].path == "charmcraft.yaml"
        assert findings[0].line is not None

    def test_legacy_config_yaml_anchors_to_that_file(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        (tmp_charm / "config.yaml").write_text(
            "options:\n  port:\n    type: int\n    description: HTTP port\n"
        )
        write_charm_source(
            tmp_charm,
            _charm("framework.observe(self.on.start, self._handler)"),
        )
        findings = [d for d in lint(tmp_charm) if d.rule_id == "FEATURES-006"]
        assert len(findings) == 1
        assert findings[0].path == "config.yaml"

    def test_config_changed_observed_suppresses(self, tmp_charm: pathlib.Path):
        assert not _lint_source(
            tmp_charm, _charm("framework.observe(self.on.config_changed, self._handler)")
        )

    def test_subscript_spelling_suppresses(self, tmp_charm: pathlib.Path):
        assert not _lint_source(
            tmp_charm,
            _charm(
                "framework.observe(self.on.start, self._handler)\n"
                "framework.observe(getattr(self.on, 'config_changed'), self._handler)"
            ),
        )

    def test_event_named_without_observing_suppresses(self, tmp_charm: pathlib.Path):
        """A charm handing the event to a library is handling config changes."""
        assert not _lint_source(
            tmp_charm,
            _charm(
                "framework.observe(self.on.start, self._handler)\n"
                "self.thing = Thing(self, refresh_event=self.on.config_changed)"
            ),
        )

    def test_no_config_options_not_flagged(self, tmp_charm: pathlib.Path):
        assert not _lint_source(
            tmp_charm,
            _charm("framework.observe(self.on.start, self._handler)"),
            options=False,
        )

    def test_charm_that_never_reads_config_not_flagged(self, tmp_charm: pathlib.Path):
        assert not _lint_source(
            tmp_charm,
            _charm("framework.observe(self.on.start, self._handler)", reads_config=False),
        )

    def test_charm_with_no_observers_not_flagged(self, tmp_charm: pathlib.Path):
        assert not _lint_source(tmp_charm, _charm("self.port = self.config['port']"))

    def test_framework_base_class_not_flagged(self, tmp_charm: pathlib.Path):
        assert not _lint_source(
            tmp_charm,
            """\
            import ops
            from ops_openstack.core import OSBaseCharm


            class TestCharm(OSBaseCharm):
                def __init__(self, framework):
                    super().__init__(framework)
                    framework.observe(self.on.start, self._handler)

                def _handler(self, event):
                    print(self.config['port'])


            ops.main(TestCharm)
            """,
        )

    def test_unconditional_reconcile_in_init_not_flagged(self, tmp_charm: pathlib.Path):
        assert not _lint_source(
            tmp_charm,
            _charm(
                "framework.observe(self.on.collect_unit_status, self._handler)\nself._reconcile()",
                body="def _reconcile(self):\n    print(self.config['port'])\n",
            ),
        )

    def test_collaborator_given_a_callback_not_flagged(self, tmp_charm: pathlib.Path):
        assert not _lint_source(
            tmp_charm,
            _charm(
                "framework.observe(self.on.start, self._handler)\n"
                "self.reconciler = Reconciler(self, self._handler)"
            ),
        )

    def test_opaque_observe_helper_not_flagged(self, tmp_charm: pathlib.Path):
        assert not _lint_source(
            tmp_charm,
            _charm(
                "framework.observe(self.on.start, self._handler)\n"
                "observe_events(self.on, ALL_EVENTS, self._handler)"
            ),
        )

    def test_unresolved_observed_event_not_flagged(self, tmp_charm: pathlib.Path):
        assert not _lint_source(
            tmp_charm,
            _charm(
                "for event in EVENTS:\n"
                "    framework.observe(self.on[event].changed, self._handler)"
            ),
        )

    def test_vendored_lib_observer_does_not_suppress(self, tmp_charm: pathlib.Path):
        lib_dir = tmp_charm / "lib" / "charms" / "someone_else" / "v0"
        lib_dir.mkdir(parents=True)
        (lib_dir / "helper.py").write_text(
            "def setup(charm):\n"
            "    charm.framework.observe(charm.on.config_changed, charm._handler)\n"
        )
        findings = _lint_source(
            tmp_charm, _charm("framework.observe(self.on.start, self._handler)")
        )
        assert len(findings) == 1

    def test_own_published_lib_observer_suppresses(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "my-charm", **_OPTIONS})
        write_charm_source(tmp_charm, _charm("framework.observe(self.on.start, self._handler)"))
        lib_dir = tmp_charm / "lib" / "charms" / "my_charm" / "v0"
        lib_dir.mkdir(parents=True)
        (lib_dir / "helper.py").write_text(
            "def setup(charm):\n"
            "    charm.framework.observe(charm.on.config_changed, charm._handler)\n"
        )
        assert not [d for d in lint(tmp_charm) if d.rule_id == "FEATURES-006"]

    def test_tests_do_not_count_as_charm_source(self, tmp_charm: pathlib.Path):
        tests_dir = tmp_charm / "tests" / "unit"
        tests_dir.mkdir(parents=True)
        (tests_dir / "test_charm.py").write_text(
            "def test_config(harness):\n    harness.charm.on.config_changed.emit()\n"
        )
        findings = _lint_source(
            tmp_charm, _charm("framework.observe(self.on.start, self._handler)")
        )
        assert len(findings) == 1
