"""Tests for charmlint rules."""

import pathlib

from charmlint._linter import lint
from charmlint._models import Severity
from tests.conftest import make_full_charm, write_charm_source, write_charmcraft_yaml


class TestMetadataRules:
    """Tests for metadata field checks."""

    def test_missing_name_is_error(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"display-name": "X"})
        report = lint(tmp_charm)
        ids = {d.rule_id for d in report.diagnostics}
        assert "META001" in ids
        meta001 = [d for d in report.diagnostics if d.rule_id == "META001"][0]
        assert meta001.severity == Severity.ERROR

    def test_full_metadata_no_meta_diagnostics(self, tmp_charm: pathlib.Path):
        make_full_charm(tmp_charm)
        report = lint(tmp_charm)
        meta_ids = {d.rule_id for d in report.diagnostics if d.rule_id.startswith("META")}
        assert not meta_ids

    def test_meta_diagnostics_path_is_charmcraft_yaml(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"display-name": "X"})
        report = lint(tmp_charm)
        meta001 = [d for d in report.diagnostics if d.rule_id == "META001"][0]
        assert meta001.path == "charmcraft.yaml"

    def test_meta_diagnostics_path_is_metadata_yaml_for_legacy_charms(
        self, tmp_charm: pathlib.Path
    ):
        (tmp_charm / "metadata.yaml").write_text("display-name: X\n")
        report = lint(tmp_charm)
        meta001 = [d for d in report.diagnostics if d.rule_id == "META001"][0]
        assert meta001.path == "metadata.yaml"

    def test_modern_charmcraft_title_and_links_satisfy_meta(self, tmp_charm: pathlib.Path):
        # Modern charmcraft.yaml uses `title` and a `links:` block instead of
        # the legacy top-level `display-name`/`docs`/`issues`/`source`.
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test-charm",
                "title": "Test Charm",
                "summary": "x",
                "description": "x",
                "links": {
                    "documentation": "https://example.com/docs",
                    "issues": "https://example.com/issues",
                    "source": "https://example.com/source",
                },
            },
        )
        report = lint(tmp_charm)
        ids = {d.rule_id for d in report.diagnostics}
        for rid in ("META002", "META005", "META006", "META007"):
            assert rid not in ids, f"{rid} should not fire for modern charmcraft.yaml"


class TestObservabilityRules:
    """Tests for COS relation checks."""

    def test_missing_cos_relations(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        report = lint(tmp_charm)
        cos_ids = {d.rule_id for d in report.diagnostics if d.rule_id.startswith("COS")}
        assert {"COS001", "COS002", "COS003", "COS004", "COS005"} <= cos_ids

    def test_cos_present_no_diagnostics(self, tmp_charm: pathlib.Path):
        make_full_charm(tmp_charm)
        report = lint(tmp_charm)
        cos_ids = {d.rule_id for d in report.diagnostics if d.rule_id.startswith("COS")}
        assert not cos_ids

    def test_ops_tracing_in_requirements(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        (tmp_charm / "requirements.txt").write_text("ops\nops-tracing\n")
        report = lint(tmp_charm)
        assert "COS005" not in {d.rule_id for d in report.diagnostics}


class TestStatusRules:
    """Tests for STS001/STS002/STS003 status reporting checks."""

    def test_missing_config_condition_without_status_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            "import ops\n\nclass C(ops.CharmBase):\n"
            "    def _on(self, _):\n"
            "        if not self.config.get('key'):\n"
            "            pass  # missing config: key — not handled with status\n",
        )
        report = lint(tmp_charm)
        assert "STS001" in {d.rule_id for d in report.diagnostics}

    def test_missing_config_with_blocked_status_passes(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            "import ops\nfrom ops import BlockedStatus\n\nclass C(ops.CharmBase):\n"
            "    def _on(self, _):\n"
            "        if not self.config.get('key'):\n"
            "            self.unit.status = BlockedStatus('missing config: key')\n",
        )
        report = lint(tmp_charm)
        assert "STS001" not in {d.rule_id for d in report.diagnostics}

    def test_missing_config_with_waiting_status_passes(self, tmp_charm: pathlib.Path):
        """WaitingStatus is a valid alternative to BlockedStatus for config checks."""
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            "import ops\nfrom ops import WaitingStatus\n\nclass C(ops.CharmBase):\n"
            "    def _on(self, _):\n"
            "        if not self.config.get('key'):\n"
            "            self.unit.status = WaitingStatus('missing config: key')\n",
        )
        report = lint(tmp_charm)
        assert "STS001" not in {d.rule_id for d in report.diagnostics}

    def test_no_condition_pattern_not_flagged(self, tmp_charm: pathlib.Path):
        """A charm that never mentions the condition should not be flagged."""
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            "import ops\n\nclass C(ops.CharmBase):\n"
            "    def _on(self, _):\n"
            "        self.unit.status = ops.BlockedStatus('missing TLS cert')\n",
        )
        report = lint(tmp_charm)
        ids = {d.rule_id for d in report.diagnostics}
        assert "STS001" not in ids
        assert "STS002" not in ids
        assert "STS003" not in ids

    def test_no_source_not_flagged(self, tmp_charm: pathlib.Path):
        """A charm with no Python source should not be flagged."""
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        report = lint(tmp_charm)
        ids = {d.rule_id for d in report.diagnostics}
        assert "STS001" not in ids
        assert "STS002" not in ids
        assert "STS003" not in ids

    def test_invalid_config_condition_without_status_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            "import ops\n\nclass C(ops.CharmBase):\n"
            "    def _on(self, _):\n"
            "        if self.config.get('combo') and self.config.get('other'):\n"
            "            pass  # invalid config combination\n",
        )
        report = lint(tmp_charm)
        assert "STS002" in {d.rule_id for d in report.diagnostics}

    def test_missing_relation_condition_without_status_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            "import ops\n\nclass C(ops.CharmBase):\n"
            "    def _on(self, _):\n"
            "        if not self.model.relations.get('db'):\n"
            "            pass  # missing relation: db\n",
        )
        report = lint(tmp_charm)
        assert "STS003" in {d.rule_id for d in report.diagnostics}


class TestDeprecatedRules:
    """Tests for deprecated API detection."""

    def test_stored_state_detected(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(tmp_charm, "class MyCharm:\n    _stored = StoredState()\n")
        report = lint(tmp_charm)
        dep_ids = {d.rule_id for d in report.diagnostics if d.rule_id.startswith("DEP")}
        assert "DEP001" in dep_ids

    def test_clean_source_no_deprecated(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(tmp_charm, "import ops\n\nclass MyCharm(ops.CharmBase): pass\n")
        report = lint(tmp_charm)
        dep_ids = {d.rule_id for d in report.diagnostics if d.rule_id.startswith("DEP")}
        assert not dep_ids

    def test_reactive_framework_import_detected(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            "from charms.reactive import when, set_flag\n\n"
            "@when('config.changed')\ndef configure():\n    set_flag('configured')\n",
        )
        report = lint(tmp_charm)
        dep_ids = {d.rule_id for d in report.diagnostics if d.rule_id.startswith("DEP")}
        assert "DEP004" in dep_ids

    def test_reactive_decorator_detected(self, tmp_charm: pathlib.Path):
        """``@when(...)`` on its own (no explicit charms.reactive import) still flags."""
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            "@when('db.available')\ndef on_db_available():\n    pass\n",
        )
        report = lint(tmp_charm)
        dep_ids = {d.rule_id for d in report.diagnostics if d.rule_id.startswith("DEP")}
        assert "DEP004" in dep_ids


class TestActionRules:
    """Tests for action quality checks."""

    def test_missing_expected_actions(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        report = lint(tmp_charm)
        act_ids = {d.rule_id for d in report.diagnostics if d.rule_id.startswith("ACT")}
        assert {"ACT001", "ACT002", "ACT003"} <= act_ids

    def test_action_aliases_accepted(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "actions": {
                    "health-check": {"description": "Check health"},
                    "stop": {"description": "Stop"},
                    "start": {"description": "Start"},
                },
            },
        )
        report = lint(tmp_charm)
        act_ids = {d.rule_id for d in report.diagnostics if d.rule_id.startswith("ACT")}
        # Aliases should satisfy ACT001, ACT002, ACT003.
        assert "ACT001" not in act_ids
        assert "ACT002" not in act_ids
        assert "ACT003" not in act_ids

    def test_action_missing_description(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "test", "actions": {"do-thing": {}}},
        )
        report = lint(tmp_charm)
        assert "ACT004" in {d.rule_id for d in report.diagnostics}

    def test_action_param_missing_description(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "actions": {
                    "do-thing": {
                        "description": "Does a thing",
                        "params": {"properties": {"verbose": {"type": "boolean"}}},
                    }
                },
            },
        )
        report = lint(tmp_charm)
        assert "ACT005" in {d.rule_id for d in report.diagnostics}

    def test_action_missing_observer_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "test", "actions": {"do-thing": {"description": "x"}}},
        )
        write_charm_source(
            tmp_charm,
            "import ops\n\nclass C(ops.CharmBase):\n    pass\n",
        )
        report = lint(tmp_charm)
        act006 = [d for d in report.diagnostics if d.rule_id == "ACT006"]
        assert act006

    def test_action_handler_incomplete_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "test", "actions": {"do-thing": {"description": "x"}}},
        )
        write_charm_source(
            tmp_charm,
            "import ops\n\n"
            "class C(ops.CharmBase):\n"
            "    def __init__(self, *args):\n"
            "        super().__init__(*args)\n"
            "        self.framework.observe(self.on.do_thing_action, self._on_do_thing)\n"
            "    def _on_do_thing(self, event):\n"
            "        pass\n",
        )
        report = lint(tmp_charm)
        act007 = [d for d in report.diagnostics if d.rule_id == "ACT007"]
        assert act007


class TestPebbleRules:
    """Tests for Pebble layer rules."""

    def test_add_layer_no_combine_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            "import ops\n\n"
            "class C(ops.CharmBase):\n"
            "    def _on(self, event):\n"
            "        c = self.unit.get_container('app')\n"
            "        c.add_layer('foo', {})\n",
        )
        report = lint(tmp_charm)
        assert "PEB001" in {d.rule_id for d in report.diagnostics}

    def test_pebble_call_without_can_connect_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            "import ops\n\n"
            "class C(ops.CharmBase):\n"
            "    def _on(self, event):\n"
            "        c = self.unit.get_container('app')\n"
            "        c.restart('svc')\n",
        )
        report = lint(tmp_charm)
        assert "PEB002" in {d.rule_id for d in report.diagnostics}

    def test_layer_service_missing_keys_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            "layer = {\n    'services': {\n        'app': {'command': 'run'},\n    }\n}\n",
        )
        report = lint(tmp_charm)
        assert "PEB003" in {d.rule_id for d in report.diagnostics}


class TestConfigRules:
    """Tests for config quality rules."""

    def test_config_missing_type(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "test", "config": {"options": {"foo": {"description": "x"}}}},
        )
        report = lint(tmp_charm)
        assert "CFG001" in {d.rule_id for d in report.diagnostics}

    def test_config_missing_default(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "config": {"options": {"foo": {"type": "string", "description": "x"}}},
            },
        )
        report = lint(tmp_charm)
        assert "CFG002" in {d.rule_id for d in report.diagnostics}


class TestFullCharm:
    """Integration test — a well-formed charm should have minimal diagnostics."""

    def test_full_charm_minimal_issues(self, tmp_charm: pathlib.Path):
        make_full_charm(tmp_charm)
        report = lint(tmp_charm)
        assert report.error_count == 0
        for d in report.diagnostics:
            assert d.severity != Severity.ERROR, f"Unexpected error: {d.rule_id} {d.message}"
