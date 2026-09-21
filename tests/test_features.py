"""Tests for FEATURES rules."""

import pathlib
import textwrap

from charmlint._linter import lint
from charmlint._models import Severity
from tests.conftest import write_charm_source, write_charmcraft_yaml


def _lint_source(charm_dir: pathlib.Path, source: str, name: str = "test"):
    """Lint a charm whose src/charm.py is *source*, returning FEATURES-001 findings."""
    write_charmcraft_yaml(charm_dir, {"name": name})
    write_charm_source(charm_dir, textwrap.dedent(source))
    report = lint(charm_dir)
    return [d for d in report if d.rule_id == "FEATURES-001"]


def _write_lib(charm_dir: pathlib.Path, owner: str, source: str) -> None:
    """Write a charm library under ``lib/charms/<owner>/v0/thing.py``."""
    directory = charm_dir / "lib" / "charms" / owner / "v0"
    directory.mkdir(parents=True)
    (directory / "thing.py").write_text(textwrap.dedent(source))


_CHARM = """\
    import ops

    class Charm(ops.CharmBase):
        def __init__(self, framework):
            super().__init__(framework)
            self.framework.observe(self.on.config_changed, self._on_event)
            {observe}

        def _on_event(self, event):
            pass

    if __name__ == "__main__":
        ops.main(Charm)
"""


def _charm(observe: str = "pass") -> str:
    """A charm that observes config-changed, plus *observe* in ``__init__``."""
    return _CHARM.format(observe=observe)


class TestNoUpgradeCharmObserver:
    """FEATURES-001 — a charm should observe the upgrade-charm event."""

    def test_no_observer_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_source(tmp_charm, _charm())
        assert len(findings) == 1
        assert findings[0].severity == Severity.INFO
        assert "upgrade-charm" in findings[0].message
        # A charm-level finding: there is no line that is missing the observer.
        assert findings[0].path is None
        assert findings[0].line is None

    def test_other_observers_do_not_suppress(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _charm("self.framework.observe(self.on.install, self._on_event)"),
        )
        assert len(findings) == 1

    def test_upgrade_charm_observer_suppresses(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _charm("self.framework.observe(self.on.upgrade_charm, self._on_event)"),
        )
        assert findings == []

    def test_bare_framework_observe_suppresses(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _charm("framework.observe(self.on.upgrade_charm, self._on_event)"),
        )
        assert findings == []

    def test_getattr_observer_suppresses(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _charm('framework.observe(getattr(self.on, "upgrade_charm"), self._on_event)'),
        )
        assert findings == []

    def test_unresolved_observer_suppresses(self, tmp_charm: pathlib.Path):
        # The event can't be read statically, so it might be upgrade-charm.
        findings = _lint_source(
            tmp_charm,
            _charm("framework.observe(getattr(self.on, EVENT), self._on_event)"),
        )
        assert findings == []

    def test_observer_in_another_src_module_suppresses(self, tmp_charm: pathlib.Path):
        write_charm_source(
            tmp_charm,
            "def wire(charm):\n"
            "    charm.framework.observe(charm.on.upgrade_charm, charm._on_event)\n",
            filename="wiring.py",
        )
        findings = _lint_source(tmp_charm, _charm())
        assert findings == []

    def test_observer_in_owned_lib_suppresses(self, tmp_charm: pathlib.Path):
        _write_lib(
            tmp_charm,
            "test_charm",
            """\
            import ops

            class Thing(ops.Object):
                def __init__(self, charm):
                    charm.framework.observe(charm.on.upgrade_charm, self._on_event)

                def _on_event(self, event):
                    pass
            """,
        )
        findings = _lint_source(tmp_charm, _charm(), name="test-charm")
        assert findings == []

    def test_observer_in_vendored_lib_does_not_suppress(self, tmp_charm: pathlib.Path):
        _write_lib(
            tmp_charm,
            "someone_else",
            """\
            import ops

            class Thing(ops.Object):
                def __init__(self, charm):
                    charm.framework.observe(charm.on.upgrade_charm, self._on_event)

                def _on_event(self, event):
                    pass
            """,
        )
        findings = _lint_source(tmp_charm, _charm(), name="test-charm")
        assert len(findings) == 1

    def test_observer_in_tests_does_not_suppress(self, tmp_charm: pathlib.Path):
        unit = tmp_charm / "tests" / "unit"
        unit.mkdir(parents=True)
        (unit / "test_charm.py").write_text(
            "def test_upgrade(harness):\n"
            "    harness.framework.observe(harness.on.upgrade_charm, None)\n"
        )
        findings = _lint_source(tmp_charm, _charm())
        assert len(findings) == 1

    def test_charmbase_recognised_by_bare_name(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            """\
            from ops import CharmBase

            class Charm(CharmBase):
                def __init__(self, framework):
                    super().__init__(framework)
                    framework.observe(self.on.config_changed, self._on_event)

                def _on_event(self, event):
                    pass
            """,
        )
        assert len(findings) == 1

    def test_charmbase_recognised_by_legacy_import(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            """\
            from ops.charm import CharmBase

            class Charm(CharmBase):
                def __init__(self, framework):
                    super().__init__(framework)
                    framework.observe(self.on.config_changed, self._on_event)

                def _on_event(self, event):
                    pass
            """,
        )
        assert len(findings) == 1

    def test_external_base_class_not_flagged(self, tmp_charm: pathlib.Path):
        # The base class is a pip dependency, so its observe calls are not
        # in the tree and the rule can't tell what it handles.
        findings = _lint_source(
            tmp_charm,
            """\
            import ops
            import paas_charm.flask

            class Charm(paas_charm.flask.Charm):
                pass

            if __name__ == "__main__":
                ops.main(Charm)
            """,
        )
        assert findings == []

    def test_event_passed_to_a_library_suppresses(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _charm("Refresher(self, refresh_events=[self.on.upgrade_charm])"),
        )
        assert findings == []

    def test_event_class_passed_to_a_helper_suppresses(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _charm("observe_events(self, (ops.UpgradeCharmEvent,), self._on_event)"),
        )
        assert findings == []

    def test_observe_helper_suppresses(self, tmp_charm: pathlib.Path):
        # The helper registers a set of events named inside it, so the
        # charm's own source doesn't say what is observed.
        findings = _lint_source(
            tmp_charm,
            _charm("observe_events(self, all_events, self._on_event)"),
        )
        assert findings == []

    def test_reconciler_object_suppresses(self, tmp_charm: pathlib.Path):
        findings = _lint_source(tmp_charm, _charm("Reconciler(self, self._reconcile)"))
        assert findings == []

    def test_charm_that_observes_nothing_not_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            """\
            import ops

            class Charm(ops.CharmBase):
                def __init__(self, framework):
                    super().__init__(framework)
                    self.reconciler = Reconciler(self, self._reconcile)

                def _reconcile(self):
                    pass
            """,
        )
        assert findings == []

    def test_hook_name_dispatch_suppresses(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _charm('if os.environ["JUJU_HOOK_NAME"] == "upgrade-charm": self._migrate()'),
        )
        assert findings == []

    def test_not_a_charm_not_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_source(tmp_charm, "VALUE = 1\n")
        assert findings == []

    def test_charm_only_in_vendored_lib_not_flagged(self, tmp_charm: pathlib.Path):
        _write_lib(
            tmp_charm,
            "someone_else",
            """\
            import ops

            class Base(ops.CharmBase):
                pass
            """,
        )
        findings = _lint_source(tmp_charm, "VALUE = 1\n", name="test-charm")
        assert findings == []


def _hits(charm_dir: pathlib.Path):
    """Lint *charm_dir*, returning the FEATURES-004 findings."""
    return [d for d in lint(charm_dir) if d.rule_id == "FEATURES-004"]


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
