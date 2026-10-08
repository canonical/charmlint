"""Tests for FEATURES-### rules."""

import pathlib
import textwrap
from typing import Any

from charmlint._linter import lint
from charmlint._models import Severity
from tests.conftest import write_charm_source, write_charmcraft_yaml

RULE_ID = "FEATURES-004"


def _hits(charm_dir: pathlib.Path):
    return [d for d in list(lint(charm_dir)) if d.rule_id == RULE_ID]


class TestNoAssumesJujuVersion:
    """Tests for FEATURES-004 — no `assumes:` Juju version constraint."""

    def test_no_assumes_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        hits = _hits(tmp_charm)
        assert len(hits) == 1
        assert hits[0].severity == Severity.INFO
        assert hits[0].path == "charmcraft.yaml"
        # There is no `assumes` key to anchor to.
        assert hits[0].line is None

    def test_empty_assumes_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x", "assumes": []})
        assert len(_hits(tmp_charm)) == 1

    def test_assumes_without_juju_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x", "assumes": ["k8s-api"]})
        hits = _hits(tmp_charm)
        assert len(hits) == 1
        # The `assumes` block exists, so the finding anchors to its key.
        assert hits[0].line is not None

    def test_string_form_suppresses(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x", "assumes": ["juju >= 3.6"]})
        assert not _hits(tmp_charm)

    def test_mapping_form_suppresses(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "x", "assumes": [{"juju": ">= 3.6"}, "k8s-api"]},
        )
        assert not _hits(tmp_charm)

    def test_upper_bound_only_suppresses(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x", "assumes": ["juju < 4"]})
        assert not _hits(tmp_charm)

    def test_any_of_group_suppresses(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "x", "assumes": [{"any-of": ["juju >= 2.9.44", "juju >= 3.1.6"]}]},
        )
        assert not _hits(tmp_charm)

    def test_nested_all_of_group_suppresses(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "x",
                "assumes": [
                    "k8s-api",
                    {"any-of": [{"all-of": ["juju >= 3.1", "k8s-api"]}, "juju >= 2.9"]},
                ],
            },
        )
        assert not _hits(tmp_charm)

    def test_group_without_juju_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "x", "assumes": [{"any-of": ["k8s-api", "shared-fs"]}]},
        )
        assert len(_hits(tmp_charm)) == 1

    def test_bare_juju_without_version_flagged(self, tmp_charm: pathlib.Path):
        # `juju` on its own is not a version constraint.
        write_charmcraft_yaml(tmp_charm, {"name": "x", "assumes": ["juju"]})
        assert len(_hits(tmp_charm)) == 1

    def test_bare_juju_mapping_without_version_flagged(self, tmp_charm: pathlib.Path):
        # `- juju:` parses to `{"juju": None}` — the mapping-form
        # equivalent of a bare `juju`, and just as much not a constraint.
        write_charmcraft_yaml(tmp_charm, {"name": "x", "assumes": [{"juju": None}]})
        assert len(_hits(tmp_charm)) == 1

    def test_juju_prefixed_feature_does_not_suppress(self, tmp_charm: pathlib.Path):
        # A hypothetical feature whose name merely starts with "juju".
        write_charmcraft_yaml(tmp_charm, {"name": "x", "assumes": ["juju-secrets"]})
        assert len(_hits(tmp_charm)) == 1

    def test_split_metadata_charm_not_flagged(self, tmp_charm: pathlib.Path):
        # `name` still lives in metadata.yaml: a pre-unification layout,
        # which the rule leaves alone.
        (tmp_charm / "charmcraft.yaml").write_text("type: charm\n")
        (tmp_charm / "metadata.yaml").write_text("name: x\n")
        assert not _hits(tmp_charm)

    def test_metadata_yaml_only_charm_not_flagged(self, tmp_charm: pathlib.Path):
        (tmp_charm / "metadata.yaml").write_text("name: x\nsummary: s\n")
        assert not _hits(tmp_charm)

    def test_anchors_at_the_assumes_key(self, tmp_charm: pathlib.Path):
        (tmp_charm / "charmcraft.yaml").write_text("name: x\nassumes:\n  - k8s-api\n")
        hits = _hits(tmp_charm)
        assert len(hits) == 1
        assert hits[0].path == "charmcraft.yaml"
        assert hits[0].line == 2

    def test_bundle_not_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"type": "bundle", "name": "x"})
        assert not _hits(tmp_charm)

    def test_malformed_assumes_flagged_not_crashed(self, tmp_charm: pathlib.Path):
        # A mapping where a list belongs: the charm declares nothing usable.
        write_charmcraft_yaml(tmp_charm, {"name": "x", "assumes": {"juju": ">= 3.6"}})
        assert len(_hits(tmp_charm)) == 1

    def test_non_scalar_assumes_entry_flagged(self, tmp_charm: pathlib.Path):
        # An entry that is neither a string nor a mapping can't name a
        # feature, so it neither satisfies nor crashes the rule.
        write_charmcraft_yaml(tmp_charm, {"name": "x", "assumes": [["juju >= 3.6"]]})
        assert len(_hits(tmp_charm)) == 1

    def test_charm_without_metadata_not_flagged(self, tmp_charm: pathlib.Path):
        # Nothing to read: METADATA-001 is the finding here, not this rule.
        assert not _hits(tmp_charm)

    def test_noqa_on_assumes_line_suppresses(self, tmp_charm: pathlib.Path):
        (tmp_charm / "charmcraft.yaml").write_text(
            "name: x\nassumes:  # noqa: FEATURES-004\n  - k8s-api\n"
        )
        assert not _hits(tmp_charm)


_CONTAINERS: dict[str, Any] = {"workload": {"resource": "workload-image"}}

_PLAIN_CHARM = """\
    import ops

    class C(ops.CharmBase):
        def _on_pebble_ready(self, event):
            event.workload.replan()
"""


def _lint(charm_dir: pathlib.Path, metadata: dict[str, Any], source: str | None = _PLAIN_CHARM):
    """Lint a charm with the given metadata and src/charm.py, returning FEATURES-005."""
    write_charmcraft_yaml(charm_dir, {"name": "test-charm", **metadata})
    if source is not None:
        write_charm_source(charm_dir, textwrap.dedent(source))
    report = lint(charm_dir)
    return [d for d in report if d.rule_id == "FEATURES-005"]


def _charm_calling(expression: str) -> str:
    """A charm source whose Pebble-ready handler makes the given call."""
    return f"""\
        import ops

        class C(ops.CharmBase):
            def _on_pebble_ready(self, event):
                {expression}
    """


class TestNoSetWorkloadVersion:
    """FEATURES-005 — a charm should report its workload's version."""

    def test_containers_without_call_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint(tmp_charm, {"containers": _CONTAINERS})
        assert len(findings) == 1
        assert findings[0].severity == Severity.INFO
        assert "set_workload_version" in findings[0].message
        assert findings[0].path == "charmcraft.yaml"
        assert findings[0].line is not None

    def test_charm_without_containers_flagged(self, tmp_charm: pathlib.Path):
        """The rule is not limited to Kubernetes charms."""
        findings = _lint(tmp_charm, {})
        assert len(findings) == 1
        assert findings[0].severity == Severity.INFO
        # Nothing as specific as a `containers:` key to point at, so the
        # finding anchors at the metadata file as a whole.
        assert findings[0].path == "charmcraft.yaml"
        assert findings[0].line is None

    def test_empty_containers_flagged(self, tmp_charm: pathlib.Path):
        assert len(_lint(tmp_charm, {"containers": {}})) == 1

    def test_machine_charm_with_call_not_flagged(self, tmp_charm: pathlib.Path):
        source = _charm_calling("self.unit.set_workload_version(self._snap_revision())")
        assert _lint(tmp_charm, {}, source) == []

    def test_integrator_name_suppresses(self, tmp_charm: pathlib.Path):
        """A name that says the charm has no workload stands in for the comment."""
        assert _lint(tmp_charm, {"name": "saml-integrator"}) == []

    def test_configurator_name_suppresses(self, tmp_charm: pathlib.Path):
        assert _lint(tmp_charm, {"name": "ingress-configurator"}) == []

    def test_interface_name_suppresses(self, tmp_charm: pathlib.Path):
        assert _lint(tmp_charm, {"name": "tls-certificates-interface"}) == []

    def test_suffix_matches_on_the_word_not_the_ending(self, tmp_charm: pathlib.Path):
        """A name merely ending in the letters is not a suffix: only `-word` is."""
        assert len(_lint(tmp_charm, {"name": "myintegrator"})) == 1

    def test_file_ignore_suppresses_a_workload_less_charm(self, tmp_charm: pathlib.Path):
        """The documented escape hatch for a charm with nothing to version."""
        (tmp_charm / "charmcraft.yaml").write_text(
            "# charmlint: file-ignore[FEATURES-005]\nname: test-charm\ntype: charm\n"
        )
        write_charm_source(tmp_charm, textwrap.dedent(_PLAIN_CHARM))
        assert [d for d in lint(tmp_charm) if d.rule_id == "FEATURES-005"] == []

    def test_self_unit_call_suppresses(self, tmp_charm: pathlib.Path):
        source = _charm_calling('self.unit.set_workload_version("1.2.3")')
        assert _lint(tmp_charm, {"containers": _CONTAINERS}, source) == []

    def test_self_model_unit_call_suppresses(self, tmp_charm: pathlib.Path):
        source = _charm_calling('self.model.unit.set_workload_version("1.2.3")')
        assert _lint(tmp_charm, {"containers": _CONTAINERS}, source) == []

    def test_call_through_a_local_suppresses(self, tmp_charm: pathlib.Path):
        source = """\
            import ops

            class C(ops.CharmBase):
                def _on_pebble_ready(self, event):
                    unit = self.unit
                    unit.set_workload_version(self._version())
        """
        assert _lint(tmp_charm, {"containers": _CONTAINERS}, source) == []

    def test_call_in_another_src_module_suppresses(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test-charm", "containers": _CONTAINERS})
        write_charm_source(tmp_charm, textwrap.dedent(_PLAIN_CHARM))
        write_charm_source(
            tmp_charm,
            "def report(unit, version):\n    unit.set_workload_version(version)\n",
            filename="workload.py",
        )
        report = lint(tmp_charm)
        assert [d for d in report if d.rule_id == "FEATURES-005"] == []

    def test_call_in_an_owned_library_suppresses(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test-charm", "containers": _CONTAINERS})
        write_charm_source(tmp_charm, textwrap.dedent(_PLAIN_CHARM))
        owned = tmp_charm / "lib" / "charms" / "test_charm" / "v0"
        owned.mkdir(parents=True)
        (owned / "helper.py").write_text(
            "def report(unit, version):\n    unit.set_workload_version(version)\n"
        )
        report = lint(tmp_charm)
        assert [d for d in report if d.rule_id == "FEATURES-005"] == []

    def test_call_in_a_vendored_library_does_not_suppress(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test-charm", "containers": _CONTAINERS})
        write_charm_source(tmp_charm, textwrap.dedent(_PLAIN_CHARM))
        vendored = tmp_charm / "lib" / "charms" / "other_charm" / "v0"
        vendored.mkdir(parents=True)
        (vendored / "helper.py").write_text(
            "def report(unit, version):\n    unit.set_workload_version(version)\n"
        )
        report = lint(tmp_charm)
        assert len([d for d in report if d.rule_id == "FEATURES-005"]) == 1

    def test_call_in_tests_does_not_suppress(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test-charm", "containers": _CONTAINERS})
        write_charm_source(tmp_charm, textwrap.dedent(_PLAIN_CHARM))
        unit_tests = tmp_charm / "tests" / "unit"
        unit_tests.mkdir(parents=True)
        (unit_tests / "test_charm.py").write_text(
            "def test_version(unit):\n    unit.set_workload_version('1')\n"
        )
        report = lint(tmp_charm)
        assert len([d for d in report if d.rule_id == "FEATURES-005"]) == 1

    def test_coordinated_workers_worker_suppresses(self, tmp_charm: pathlib.Path):
        source = """\
            from coordinated_workers.worker import Worker

            class C(ops.CharmBase):
                def __init__(self, framework):
                    super().__init__(framework)
                    self._worker = Worker(self, "workload", self._layer, {})
        """
        assert _lint(tmp_charm, {"containers": _CONTAINERS}, source) == []

    def test_coordinated_workers_worker_subclass_suppresses(self, tmp_charm: pathlib.Path):
        source = """\
            import coordinated_workers.worker

            class MyWorker(coordinated_workers.worker.Worker):
                pass
        """
        assert _lint(tmp_charm, {"containers": _CONTAINERS}, source) == []

    def test_coordinated_workers_coordinator_does_not_suppress(self, tmp_charm: pathlib.Path):
        source = """\
            from coordinated_workers.coordinator import Coordinator
            from coordinated_workers.worker_telemetry import WorkerTelemetryProxyConfig

            class C(ops.CharmBase):
                def __init__(self, framework):
                    super().__init__(framework)
                    self.coordinator = Coordinator(self)
        """
        assert len(_lint(tmp_charm, {"containers": _CONTAINERS}, source)) == 1

    def test_charm_with_no_source_not_flagged(self, tmp_charm: pathlib.Path):
        assert _lint(tmp_charm, {"containers": _CONTAINERS}, source=None) == []

    def test_similarly_named_call_does_not_suppress(self, tmp_charm: pathlib.Path):
        source = _charm_calling('self.unit.set_workload_versions("1.2.3")')
        assert len(_lint(tmp_charm, {"containers": _CONTAINERS}, source)) == 1

    def test_anchors_to_the_metadata_yaml_containers_key(self, tmp_charm: pathlib.Path):
        (tmp_charm / "charmcraft.yaml").write_text("name: test-charm\ntype: charm\n")
        (tmp_charm / "metadata.yaml").write_text(
            "name: test-charm\ncontainers:\n  workload:\n    resource: workload-image\n"
        )
        write_charm_source(tmp_charm, textwrap.dedent(_PLAIN_CHARM))
        findings = [d for d in lint(tmp_charm) if d.rule_id == "FEATURES-005"]
        assert len(findings) == 1
        assert findings[0].path == "metadata.yaml"
        assert findings[0].line == 2

    def test_noqa_on_the_containers_line_suppresses(self, tmp_charm: pathlib.Path):
        (tmp_charm / "charmcraft.yaml").write_text(
            "name: test-charm\n"
            "containers:  # noqa: FEATURES-005\n"
            "  workload:\n"
            "    resource: workload-image\n"
        )
        write_charm_source(tmp_charm, textwrap.dedent(_PLAIN_CHARM))
        assert [d for d in lint(tmp_charm) if d.rule_id == "FEATURES-005"] == []

    def test_charmhelpers_application_version_set_suppresses(self, tmp_charm: pathlib.Path):
        """A reactive charm reports the same Juju field by another name."""
        source = """\
            from charmhelpers.core import hookenv

            def set_version():
                hookenv.application_version_set("1.2.3")
        """
        assert _lint(tmp_charm, {}, source) == []

    def test_bare_application_version_set_suppresses(self, tmp_charm: pathlib.Path):
        source = """\
            from charmhelpers.core.hookenv import application_version_set

            def set_version():
                application_version_set("1.2.3")
        """
        assert _lint(tmp_charm, {}, source) == []


class TestHardcodedWorkloadVersion:
    """FEATURES-006 — the reported version should be read, not written down."""

    def _findings(self, charm_dir: pathlib.Path, source: str):
        write_charmcraft_yaml(charm_dir, {"name": "test-charm", "containers": _CONTAINERS})
        write_charm_source(charm_dir, textwrap.dedent(source))
        return [d for d in lint(charm_dir) if d.rule_id == "FEATURES-006"]

    def test_string_literal_flagged(self, tmp_charm: pathlib.Path):
        findings = self._findings(
            tmp_charm, _charm_calling('self.unit.set_workload_version("1.2.3")')
        )
        assert len(findings) == 1
        assert findings[0].severity == Severity.WARNING
        assert "1.2.3" in findings[0].message
        assert findings[0].path == "src/charm.py"
        assert findings[0].line is not None

    def test_module_constant_flagged(self, tmp_charm: pathlib.Path):
        source = """\
            import ops

            WORKLOAD_VERSION = "2.27.1"

            class C(ops.CharmBase):
                def _on_pebble_ready(self, event):
                    self.unit.set_workload_version(WORKLOAD_VERSION)
        """
        findings = self._findings(tmp_charm, source)
        assert len(findings) == 1
        # The message quotes the version that reaches Juju, not the name it
        # was written under: the path and line already point at the name.
        assert "2.27.1" in findings[0].message

    def test_constant_named_like_a_placeholder_flagged(self, tmp_charm: pathlib.Path):
        """A real version is hardcoded however the name reads."""
        source = """\
            import ops

            UNKNOWN = "1.2.3"

            class C(ops.CharmBase):
                def _on_pebble_ready(self, event):
                    self.unit.set_workload_version(UNKNOWN)
        """
        findings = self._findings(tmp_charm, source)
        assert len(findings) == 1
        assert "1.2.3" in findings[0].message

    def test_name_bound_to_a_placeholder_not_flagged(self, tmp_charm: pathlib.Path):
        """A placeholder is a placeholder whether or not it is named one."""
        source = """\
            import ops

            VERSION = "n/a"

            class C(ops.CharmBase):
                def _on_stop(self, event):
                    self.unit.set_workload_version(VERSION)
        """
        assert self._findings(tmp_charm, source) == []

    def test_charmhelpers_spelling_flagged(self, tmp_charm: pathlib.Path):
        source = """\
            from charmhelpers.core import hookenv

            def report():
                hookenv.application_version_set("1.2.3")
        """
        assert len(self._findings(tmp_charm, source)) == 1

    def test_value_read_from_the_workload_not_flagged(self, tmp_charm: pathlib.Path):
        source = _charm_calling("self.unit.set_workload_version(self._workload_version())")
        assert self._findings(tmp_charm, source) == []

    def test_attribute_not_flagged(self, tmp_charm: pathlib.Path):
        source = _charm_calling("self.unit.set_workload_version(self.workload.version)")
        assert self._findings(tmp_charm, source) == []

    def test_empty_string_not_flagged(self, tmp_charm: pathlib.Path):
        """Clearing the field on teardown is not a hardcoded version."""
        source = _charm_calling('self.unit.set_workload_version("")')
        assert self._findings(tmp_charm, source) == []

    def test_n_a_placeholder_not_flagged(self, tmp_charm: pathlib.Path):
        source = _charm_calling('self.unit.set_workload_version("n/a")')
        assert self._findings(tmp_charm, source) == []

    def test_or_fallback_not_flagged(self, tmp_charm: pathlib.Path):
        """The COS `Worker` idiom: a real lookup with a placeholder fallback."""
        source = _charm_calling('self.unit.set_workload_version(self.running_version() or "")')
        assert self._findings(tmp_charm, source) == []

    def test_name_reassigned_dynamically_not_flagged(self, tmp_charm: pathlib.Path):
        source = """\
            import ops

            class C(ops.CharmBase):
                def _on_pebble_ready(self, event):
                    version = "unknown"
                    if self._can_ask():
                        version = self._workload_version()
                    self.unit.set_workload_version(version)
        """
        assert self._findings(tmp_charm, source) == []

    def test_constant_from_another_module_not_followed(self, tmp_charm: pathlib.Path):
        """A deliberate gap: no corpus finding needs it, and it risks FPs."""
        source = """\
            import ops

            from constants import WORKLOAD_VERSION

            class C(ops.CharmBase):
                def _on_pebble_ready(self, event):
                    self.unit.set_workload_version(WORKLOAD_VERSION)
        """
        write_charm_source(tmp_charm, 'WORKLOAD_VERSION = "1.2.3"\n', filename="constants.py")
        assert self._findings(tmp_charm, source) == []

    def test_no_argument_not_flagged(self, tmp_charm: pathlib.Path):
        source = _charm_calling("self.unit.set_workload_version()")
        assert self._findings(tmp_charm, source) == []

    def test_each_call_site_reported(self, tmp_charm: pathlib.Path):
        source = """\
            import ops

            class C(ops.CharmBase):
                def _on_install(self, event):
                    self.unit.set_workload_version("1.0.0")

                def _on_upgrade(self, event):
                    self.unit.set_workload_version("1.0.0")
        """
        assert len(self._findings(tmp_charm, source)) == 2

    def test_does_not_fire_when_005_does(self, tmp_charm: pathlib.Path):
        """The two rules are about opposite problems and never overlap."""
        write_charmcraft_yaml(tmp_charm, {"name": "test-charm", "containers": _CONTAINERS})
        write_charm_source(tmp_charm, textwrap.dedent(_PLAIN_CHARM))
        ids = {d.rule_id for d in lint(tmp_charm)}
        assert "FEATURES-005" in ids
        assert "FEATURES-006" not in ids


_OPTIONS = {"config": {"options": {"port": {"type": "int", "description": "HTTP port"}}}}


def _lint_source(charm_dir: pathlib.Path, source: str, *, options: bool = True):
    """Lint a charm whose ``src/charm.py`` is *source*, returning FEATURES-007 findings."""
    metadata: dict[str, object] = {"name": "test"}
    if options:
        metadata.update(_OPTIONS)
    write_charmcraft_yaml(charm_dir, metadata)
    write_charm_source(charm_dir, textwrap.dedent(source))
    return [d for d in lint(charm_dir) if d.rule_id == "FEATURES-007"]


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
    """FEATURES-007 — declared config options with nothing handling a change."""

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
        findings = [d for d in lint(tmp_charm) if d.rule_id == "FEATURES-007"]
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
        assert not [d for d in lint(tmp_charm) if d.rule_id == "FEATURES-007"]

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
