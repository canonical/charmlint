"""Tests for charmlint rules."""

import pathlib

from charmlint._linter import lint
from charmlint._models import Severity
from tests.conftest import (
    make_full_charm,
    write_charm_source,
    write_charmcraft_yaml,
)


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


class TestObservabilityRules:
    """Tests for COS and ops-tracing checks."""

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


class TestTestingRules:
    """Tests for test presence and framework usage."""

    def test_no_tests_detected(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        report = lint(tmp_charm)
        ids = {d.rule_id for d in report.diagnostics}
        assert "TEST001" in ids
        assert "TEST002" in ids

    def test_with_tests_present(self, tmp_charm: pathlib.Path):
        make_full_charm(tmp_charm)
        report = lint(tmp_charm)
        test_ids = {d.rule_id for d in report.diagnostics if d.rule_id.startswith("TEST")}
        assert not test_ids

    def test_harness_detected(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        (tmp_charm / "tests").mkdir()
        (tmp_charm / "tests" / "test_charm.py").write_text("from ops.testing import Harness\n")
        report = lint(tmp_charm)
        assert "TEST003" in {d.rule_id for d in report.diagnostics}


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


class TestLibraryRules:
    """Tests for fetch-libs PyPI checks."""

    def test_known_pypi_detected(self, tmp_charm: pathlib.Path):
        """tls_certificates_interface has a real PyPI replacement."""
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            (
                "from charms.tls_certificates_interface.v3.tls_certificates "
                "import TLSCertificatesRequiresV3\n"
            ),
        )
        report = lint(tmp_charm)
        diagnostics = {d.rule_id: d.message for d in report.diagnostics}
        assert "LIB001" in diagnostics
        # Ensure the new import hint is surfaced to the user.
        assert "charmlibs-interfaces-tls-certificates" in diagnostics["LIB001"]
        assert "from charmlibs.interfaces import tls_certificates" in diagnostics["LIB001"]

    def test_operator_libs_linux_submodule_detected(self, tmp_charm: pathlib.Path):
        """``operator_libs_linux`` splits by submodule — ``apt`` → ``charmlibs-apt``."""
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm, "from charms.operator_libs_linux.v0.apt import DebianPackage\n"
        )
        report = lint(tmp_charm)
        diagnostics = {d.rule_id: d.message for d in report.diagnostics}
        assert "LIB001" in diagnostics
        assert "charmlibs-apt" in diagnostics["LIB001"]

    def test_observability_libs_still_need_fetch_libs(self, tmp_charm: pathlib.Path):
        """grafana_k8s has no PyPI equivalent yet — LIB002, not LIB001."""
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm, "from charms.grafana_k8s.v0.grafana_dashboard import GrafanaDashboard\n"
        )
        report = lint(tmp_charm)
        rule_ids = {d.rule_id for d in report.diagnostics}
        assert "LIB002" in rule_ids
        assert "LIB001" not in rule_ids

    def test_unknown_lib_detected(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(tmp_charm, "from charms.my_custom_lib.v1.module import Foo\n")
        report = lint(tmp_charm)
        assert "LIB002" in {d.rule_id for d in report.diagnostics}


class TestLibraryVersions:
    """Tests for LIB003/LIB004 (library metadata + breaking-change)."""

    @staticmethod
    def _write_lib(charm: pathlib.Path, charm_name: str, api: int, name: str, body: str) -> None:
        lib_dir = charm / "lib" / "charms" / charm_name / f"v{api}"
        lib_dir.mkdir(parents=True, exist_ok=True)
        (lib_dir / f"{name}.py").write_text(body)

    def test_library_with_full_metadata_passes(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        self._write_lib(
            tmp_charm,
            "test_charm",
            0,
            "thing",
            "LIBID = 'a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4'\nLIBAPI = 0\nLIBPATCH = 1\nPYDEPS = []\n",
        )
        report = lint(tmp_charm)
        assert "LIB003" not in {d.rule_id for d in report.diagnostics}

    def test_library_missing_libid_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        self._write_lib(tmp_charm, "test_charm", 0, "thing", "LIBAPI = 0\nLIBPATCH = 1\n")
        report = lint(tmp_charm)
        msgs = [d.message for d in report.diagnostics if d.rule_id == "LIB003"]
        assert any("LIBID" in m for m in msgs)

    def test_library_libapi_dir_mismatch_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        # File is in v0/ but LIBAPI says 1.
        self._write_lib(
            tmp_charm,
            "test_charm",
            0,
            "thing",
            "LIBID = 'a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4'\nLIBAPI = 1\nLIBPATCH = 0\n",
        )
        report = lint(tmp_charm)
        lib003 = [d for d in report.diagnostics if d.rule_id == "LIB003"]
        assert any("does not match directory v0" in d.message for d in lib003)

    def test_library_breaking_change_detected(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        self._write_lib(
            tmp_charm,
            "test_charm",
            0,
            "thing",
            "LIBID = 'a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4'\n"
            "LIBAPI = 0\nLIBPATCH = 7\n\nclass Foo:\n    pass\n\nclass Bar:\n    pass\n",
        )
        # v1 drops Bar.
        self._write_lib(
            tmp_charm,
            "test_charm",
            1,
            "thing",
            "LIBID = 'a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4'\n"
            "LIBAPI = 1\nLIBPATCH = 0\n\nclass Foo:\n    pass\n",
        )
        report = lint(tmp_charm)
        lib004 = [d for d in report.diagnostics if d.rule_id == "LIB004"]
        assert len(lib004) == 1
        assert "Bar" in lib004[0].message

    def test_library_additive_change_passes(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        self._write_lib(
            tmp_charm,
            "test_charm",
            0,
            "thing",
            "LIBID = 'a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4'\n"
            "LIBAPI = 0\nLIBPATCH = 1\n\nclass Foo:\n    pass\n",
        )
        # v1 adds Bar but keeps Foo.
        self._write_lib(
            tmp_charm,
            "test_charm",
            1,
            "thing",
            "LIBID = 'a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4'\n"
            "LIBAPI = 1\nLIBPATCH = 0\n\nclass Foo:\n    pass\n\nclass Bar:\n    pass\n",
        )
        report = lint(tmp_charm)
        assert "LIB004" not in {d.rule_id for d in report.diagnostics}


class TestRelationDataRules:
    """Tests for REL001/REL002 (relation-data guards)."""

    def test_unguarded_app_subscript_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            "import ops\n\nclass C(ops.CharmBase):\n"
            "    def _on_db_changed(self, event):\n"
            "        data = event.relation.data[event.app]\n"
            "        host = data.get('host')\n",
        )
        report = lint(tmp_charm)
        rel001 = [d for d in report.diagnostics if d.rule_id == "REL001"]
        assert len(rel001) == 1
        assert "_on_db_changed" in rel001[0].message

    def test_app_subscript_with_guard_passes(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            "import ops\n\nclass C(ops.CharmBase):\n"
            "    def _on_db_changed(self, event):\n"
            "        if event.app is None:\n"
            "            return\n"
            "        data = event.relation.data[event.app]\n",
        )
        report = lint(tmp_charm)
        assert "REL001" not in {d.rule_id for d in report.diagnostics}

    def test_app_data_get_form_passes(self, tmp_charm: pathlib.Path):
        """`event.relation.data.get(event.app)` is intrinsically safe."""
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            "import ops\n\nclass C(ops.CharmBase):\n"
            "    def _on_db_changed(self, event):\n"
            "        data = event.relation.data.get(event.app, {})\n"
            "        host = data.get('host')\n",
        )
        report = lint(tmp_charm)
        assert "REL001" not in {d.rule_id for d in report.diagnostics}

    def test_app_write_without_leader_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            "import ops\n\nclass C(ops.CharmBase):\n"
            "    def _on_website_joined(self, event):\n"
            "        event.relation.data[self.app]['url'] = 'http://x'\n",
        )
        report = lint(tmp_charm)
        rel002 = [d for d in report.diagnostics if d.rule_id == "REL002"]
        assert len(rel002) == 1
        assert "_on_website_joined" in rel002[0].message

    def test_app_write_with_leader_guard_passes(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            "import ops\n\nclass C(ops.CharmBase):\n"
            "    def _on_website_joined(self, event):\n"
            "        if not self.unit.is_leader():\n"
            "            return\n"
            "        event.relation.data[self.app]['url'] = 'http://x'\n",
        )
        report = lint(tmp_charm)
        assert "REL002" not in {d.rule_id for d in report.diagnostics}


class TestPebbleRules:
    """Tests for PEB001/PEB002/PEB003 (Pebble layer hygiene)."""

    def test_add_layer_no_combine_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            "import ops\n\nclass C(ops.CharmBase):\n"
            "    def _on_pebble_ready(self, event):\n"
            "        self._container.add_layer('app', {})\n",
        )
        report = lint(tmp_charm)
        assert "PEB001" in {d.rule_id for d in report.diagnostics}

    def test_add_layer_with_combine_passes(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            "import ops\n\nclass C(ops.CharmBase):\n"
            "    def _on_pebble_ready(self, event):\n"
            "        self._container.add_layer('app', {}, combine=True)\n",
        )
        report = lint(tmp_charm)
        assert "PEB001" not in {d.rule_id for d in report.diagnostics}

    def test_pebble_call_without_can_connect_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            "import ops\n\nclass C(ops.CharmBase):\n"
            "    def _on_config_changed(self, event):\n"
            "        self._container.add_layer('app', {}, combine=True)\n"
            "        self._container.replan()\n",
        )
        report = lint(tmp_charm)
        peb002 = [d for d in report.diagnostics if d.rule_id == "PEB002"]
        assert len(peb002) == 1
        assert "_on_config_changed" in peb002[0].message

    def test_pebble_call_with_can_connect_passes(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            "import ops\n\nclass C(ops.CharmBase):\n"
            "    def _on_config_changed(self, event):\n"
            "        if not self._container.can_connect():\n"
            "            event.defer()\n"
            "            return\n"
            "        self._container.replan()\n",
        )
        report = lint(tmp_charm)
        assert "PEB002" not in {d.rule_id for d in report.diagnostics}

    def test_pebble_call_guarded_by_caller_passes(self, tmp_charm: pathlib.Path):
        """A helper called only from a guarded caller is itself treated as guarded."""
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            "import ops\n\nclass C(ops.CharmBase):\n"
            "    def _reconcile(self, _):\n"
            "        if not self._container.can_connect():\n"
            "            return\n"
            "        self._migrate()\n"
            "    def _migrate(self):\n"
            "        self._container.exec(['true'])\n",
        )
        report = lint(tmp_charm)
        assert "PEB002" not in {d.rule_id for d in report.diagnostics}

    def test_pebble_ready_handler_skipped(self, tmp_charm: pathlib.Path):
        """The pebble_ready handler runs when Pebble is reachable; no guard needed."""
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            "import ops\n\nclass C(ops.CharmBase):\n"
            "    def _on_pebble_ready(self, event):\n"
            "        self._container.add_layer('app', {}, combine=True)\n"
            "        self._container.autostart()\n",
        )
        report = lint(tmp_charm)
        assert "PEB002" not in {d.rule_id for d in report.diagnostics}

    def test_layer_service_missing_keys_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            "import ops\n\nclass C(ops.CharmBase):\n"
            "    def _layer(self):\n"
            "        return {\n"
            "            'services': {\n"
            "                'app': {'command': '/bin/app'},\n"
            "            },\n"
            "        }\n",
        )
        report = lint(tmp_charm)
        peb003 = [d for d in report.diagnostics if d.rule_id == "PEB003"]
        assert len(peb003) == 1
        msg = peb003[0].message
        assert "override" in msg
        assert "startup" in msg

    def test_layer_service_full_keys_passes(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            "import ops\n\nclass C(ops.CharmBase):\n"
            "    def _layer(self):\n"
            "        return {\n"
            "            'summary': 'app',\n"
            "            'services': {\n"
            "                'app': {\n"
            "                    'override': 'replace',\n"
            "                    'command': '/bin/app',\n"
            "                    'startup': 'enabled',\n"
            "                },\n"
            "            },\n"
            "        }\n",
        )
        report = lint(tmp_charm)
        assert "PEB003" not in {d.rule_id for d in report.diagnostics}


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
            {"name": "test", "actions": {"backup": {}}},
        )
        report = lint(tmp_charm)
        assert "ACT004" in {d.rule_id for d in report.diagnostics}

    def test_action_missing_observer_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "test", "actions": {"backup": {"description": "x"}}},
        )
        write_charm_source(
            tmp_charm,
            "import ops\n\nclass C(ops.CharmBase):\n"
            "    def __init__(self, *args):\n        super().__init__(*args)\n",
        )
        report = lint(tmp_charm)
        act006 = [d for d in report.diagnostics if d.rule_id == "ACT006"]
        assert len(act006) == 1
        assert "backup" in act006[0].message

    def test_action_with_observer_passes(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "test", "actions": {"backup": {"description": "x"}}},
        )
        write_charm_source(
            tmp_charm,
            "import ops\n\nclass C(ops.CharmBase):\n"
            "    def __init__(self, *args):\n"
            "        super().__init__(*args)\n"
            "        self.framework.observe(self.on.backup_action, self._on_backup)\n"
            "    def _on_backup(self, event):\n"
            "        event.set_results({'ok': True})\n",
        )
        report = lint(tmp_charm)
        assert "ACT006" not in {d.rule_id for d in report.diagnostics}
        assert "ACT007" not in {d.rule_id for d in report.diagnostics}

    def test_action_hyphen_to_underscore_observer(self, tmp_charm: pathlib.Path):
        """``rotate-credentials`` in YAML matches ``rotate_credentials_action`` event."""
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "test", "actions": {"rotate-credentials": {"description": "x"}}},
        )
        write_charm_source(
            tmp_charm,
            "import ops\n\nclass C(ops.CharmBase):\n"
            "    def __init__(self, *args):\n"
            "        super().__init__(*args)\n"
            "        self.framework.observe(\n"
            "            self.on.rotate_credentials_action, self._on_rotate\n"
            "        )\n"
            "    def _on_rotate(self, event):\n"
            "        event.fail('not yet')\n",
        )
        report = lint(tmp_charm)
        act_ids = {d.rule_id for d in report.diagnostics if d.rule_id.startswith("ACT00")}
        assert "ACT006" not in act_ids
        assert "ACT007" not in act_ids

    def test_action_handler_incomplete_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "test", "actions": {"backup": {"description": "x"}}},
        )
        write_charm_source(
            tmp_charm,
            "import ops\n\nclass C(ops.CharmBase):\n"
            "    def __init__(self, *args):\n"
            "        super().__init__(*args)\n"
            "        self.framework.observe(self.on.backup_action, self._on_backup)\n"
            "    def _on_backup(self, event):\n"
            "        event.log('starting')\n",
        )
        report = lint(tmp_charm)
        act007 = [d for d in report.diagnostics if d.rule_id == "ACT007"]
        assert len(act007) == 1
        assert "_on_backup" in act007[0].message
        assert act007[0].line is not None

    def test_action_handler_fail_only_passes(self, tmp_charm: pathlib.Path):
        """A leader-only action that calls ``event.fail()`` and returns is complete."""
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "test", "actions": {"rotate": {"description": "x"}}},
        )
        write_charm_source(
            tmp_charm,
            "import ops\n\nclass C(ops.CharmBase):\n"
            "    def __init__(self, *args):\n"
            "        super().__init__(*args)\n"
            "        self.framework.observe(self.on.rotate_action, self._on_rotate)\n"
            "    def _on_rotate(self, event):\n"
            "        if not self.unit.is_leader():\n"
            "            event.fail('leader only')\n"
            "            return\n"
            "        event.set_results({'ok': True})\n",
        )
        report = lint(tmp_charm)
        assert "ACT007" not in {d.rule_id for d in report.diagnostics}

    def test_act007_skipped_when_no_observer(self, tmp_charm: pathlib.Path):
        """If the observer is missing, ACT006 fires but ACT007 stays quiet."""
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "test", "actions": {"backup": {"description": "x"}}},
        )
        write_charm_source(
            tmp_charm,
            "import ops\n\nclass C(ops.CharmBase):\n"
            "    def __init__(self, *args):\n        super().__init__(*args)\n",
        )
        report = lint(tmp_charm)
        ids = {d.rule_id for d in report.diagnostics}
        assert "ACT006" in ids
        assert "ACT007" not in ids


class TestConfigRules:
    """Tests for config option quality checks."""

    def test_config_missing_fields(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "test", "config": {"options": {"port": {}}}},
        )
        report = lint(tmp_charm)
        cfg_ids = {d.rule_id for d in report.diagnostics if d.rule_id.startswith("CFG")}
        assert {"CFG001", "CFG002", "CFG003"} <= cfg_ids

    def test_config_complete_no_diagnostics(self, tmp_charm: pathlib.Path):
        make_full_charm(tmp_charm)
        report = lint(tmp_charm)
        cfg_ids = {d.rule_id for d in report.diagnostics if d.rule_id.startswith("CFG")}
        assert not cfg_ids

    def test_config_option_unread_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "config": {
                    "options": {
                        "port": {"type": "int", "default": 8080, "description": "x"},
                        "unused": {"type": "string", "default": "y", "description": "x"},
                    }
                },
            },
        )
        write_charm_source(
            tmp_charm,
            "import ops\n\nclass C(ops.CharmBase):\n"
            "    def _on_config_changed(self, event):\n"
            "        port = self.config['port']\n"
            "        if not port:\n"
            "            self.unit.status = ops.BlockedStatus('bad port')\n",
        )
        report = lint(tmp_charm)
        cfg004 = [d for d in report.diagnostics if d.rule_id == "CFG004"]
        assert len(cfg004) == 1
        assert "unused" in cfg004[0].message

    def test_config_option_get_form_satisfies_unread(self, tmp_charm: pathlib.Path):
        """``self.config.get('log-level', 'info')`` counts as a read."""
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "config": {
                    "options": {
                        "log-level": {
                            "type": "string",
                            "default": "info",
                            "description": "x",
                        }
                    }
                },
            },
        )
        write_charm_source(
            tmp_charm,
            "import ops\n\nclass C(ops.CharmBase):\n"
            "    def _on_config_changed(self, event):\n"
            "        level = self.config.get('log-level', 'info')\n"
            "        if level not in ('debug', 'info'):\n"
            "            self.unit.status = ops.BlockedStatus('bad level')\n",
        )
        report = lint(tmp_charm)
        assert "CFG004" not in {d.rule_id for d in report.diagnostics}

    def test_config_no_blocked_status_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "config": {
                    "options": {
                        "port": {"type": "int", "default": 8080, "description": "x"},
                    }
                },
            },
        )
        write_charm_source(
            tmp_charm,
            "import ops\n\nclass C(ops.CharmBase):\n"
            "    def _on_config_changed(self, event):\n"
            "        port = self.config['port']\n"
            "        self._apply(port)\n",
        )
        report = lint(tmp_charm)
        assert "CFG005" in {d.rule_id for d in report.diagnostics}

    def test_config_with_blocked_status_passes(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "config": {
                    "options": {
                        "port": {"type": "int", "default": 8080, "description": "x"},
                    }
                },
            },
        )
        write_charm_source(
            tmp_charm,
            "import ops\nfrom ops import BlockedStatus\n\nclass C(ops.CharmBase):\n"
            "    def _on_config_changed(self, event):\n"
            "        port = self.config['port']\n"
            "        if not port:\n"
            "            self.unit.status = BlockedStatus('bad port')\n",
        )
        report = lint(tmp_charm)
        assert "CFG005" not in {d.rule_id for d in report.diagnostics}

    def test_no_config_options_skips_cfg004_cfg005(self, tmp_charm: pathlib.Path):
        """A charm without config options should not trip CFG004 or CFG005."""
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            "import ops\n\nclass C(ops.CharmBase): pass\n",
        )
        report = lint(tmp_charm)
        ids = {d.rule_id for d in report.diagnostics}
        assert "CFG004" not in ids
        assert "CFG005" not in ids


class TestSecurityRules:
    """Tests for security checks."""

    def test_secret_in_plain_config(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "config": {
                    "options": {
                        "admin-password": {"type": "string", "description": "Admin password"},
                    },
                },
            },
        )
        write_charm_source(tmp_charm, "import ops\n")
        report = lint(tmp_charm)
        assert "SEC001" in {d.rule_id for d in report.diagnostics}

    def test_secret_with_juju_secrets_ok(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "config": {
                    "options": {
                        "admin-password": {"type": "string", "description": "Password"},
                    },
                },
            },
        )
        write_charm_source(tmp_charm, "import ops\n# Uses juju secret API\nSecretChanged\n")
        report = lint(tmp_charm)
        assert "SEC001" not in {d.rule_id for d in report.diagnostics}

    def test_secret_with_ops_add_secret_ok(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "config": {
                    "options": {
                        "smtp-password": {"type": "string", "description": "smtp password"},
                    },
                },
            },
        )
        write_charm_source(
            tmp_charm,
            "import ops\n"
            "class C(ops.CharmBase):\n"
            "    def _on(self, _):\n"
            "        self.app.add_secret({'k': 'v'})\n"
            "        self.model.get_secret(label='x')\n",
        )
        report = lint(tmp_charm)
        assert "SEC001" not in {d.rule_id for d in report.diagnostics}

    def test_secret_typed_config_option_not_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "config": {
                    "options": {
                        "smtp-password": {"type": "secret", "description": "smtp creds"},
                    },
                },
            },
        )
        write_charm_source(tmp_charm, "import ops\n")
        report = lint(tmp_charm)
        assert "SEC001" not in {d.rule_id for d in report.diagnostics}

    def test_sec006_machine_charm_urlopen_without_hashlib_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            "import urllib.request\n"
            "def install():\n"
            "    urllib.request.urlopen('https://example.com/x.tar.gz')\n",
        )
        report = lint(tmp_charm)
        hits = [d for d in report.diagnostics if d.rule_id == "SEC006"]
        assert len(hits) == 1
        assert hits[0].severity == Severity.WARNING

    def test_sec006_hashlib_in_same_function_suppresses(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            "import hashlib\n"
            "import urllib.request\n"
            "def install():\n"
            "    data = urllib.request.urlopen('https://example.com/x').read()\n"
            "    digest = hashlib.sha256(data).hexdigest()\n"
            "    assert digest == 'abc'\n",
        )
        report = lint(tmp_charm)
        assert "SEC006" not in {d.rule_id for d in report.diagnostics}

    def test_sec006_k8s_charm_with_containers_not_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "containers": {"workload": {"resource": "workload-image"}},
            },
        )
        write_charm_source(
            tmp_charm,
            "import urllib.request\n"
            "def install():\n"
            "    urllib.request.urlopen('https://example.com/x')\n",
        )
        report = lint(tmp_charm)
        assert "SEC006" not in {d.rule_id for d in report.diagnostics}

    def test_sec006_requests_get_without_check_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            "import requests\ndef fetch():\n    requests.get('https://example.com/x')\n",
        )
        report = lint(tmp_charm)
        hits = [d for d in report.diagnostics if d.rule_id == "SEC006"]
        assert len(hits) == 1

    def test_sec006_wget_subprocess_without_check_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            "import subprocess\n"
            "def install():\n"
            "    subprocess.run(['wget', 'https://example.com/x'])\n",
        )
        report = lint(tmp_charm)
        hits = [d for d in report.diagnostics if d.rule_id == "SEC006"]
        assert len(hits) == 1

    def test_sec006_ignores_lib_directory(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        lib = tmp_charm / "lib" / "charms" / "other" / "v0"
        lib.mkdir(parents=True)
        (lib / "thing.py").write_text(
            "import urllib.request\n"
            "def install():\n"
            "    urllib.request.urlopen('https://example.com/x')\n",
        )
        report = lint(tmp_charm)
        assert "SEC006" not in {d.rule_id for d in report.diagnostics}

    def test_sec006_sha256sum_subprocess_suppresses(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            "import subprocess\n"
            "def install():\n"
            "    subprocess.run(['wget', 'https://example.com/x'])\n"
            "    subprocess.run(['sha256sum', '-c', 'sums.txt'], check=True)\n",
        )
        report = lint(tmp_charm)
        assert "SEC006" not in {d.rule_id for d in report.diagnostics}


class TestDocumentationRules:
    """Tests for DOC* rules (README and docs/ presence)."""

    def test_monorepo_shared_docs_satisfy_doc_topics(self, tmp_path: pathlib.Path):
        # Monorepo layout: <repo>/.git, <repo>/docs/, <repo>/charms/<name>/.
        repo = tmp_path / "repo"
        (repo / ".git").mkdir(parents=True)
        (repo / "docs").mkdir()
        (repo / "docs" / "install.md").write_text("# Installation\n\nrun foo")
        (repo / "docs" / "troubleshoot.md").write_text("# Troubleshooting\n")
        charm_dir = repo / "charms" / "alpha"
        (charm_dir / "src").mkdir(parents=True)
        write_charmcraft_yaml(charm_dir, {"name": "alpha"})
        report = lint(charm_dir)
        ids = {d.rule_id for d in report.diagnostics}
        assert "DOC002" not in ids
        assert "DOC005" not in ids


class TestStructureRules:
    """Tests for structure/file presence checks."""

    def test_missing_files_detected(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        report = lint(tmp_charm)
        str_ids = {d.rule_id for d in report.diagnostics if d.rule_id.startswith("STR")}
        assert {"STR001", "STR002", "STR003"} <= str_ids

    def test_all_files_present(self, tmp_charm: pathlib.Path):
        make_full_charm(tmp_charm)
        report = lint(tmp_charm)
        str_ids = {d.rule_id for d in report.diagnostics if d.rule_id.startswith("STR")}
        assert not str_ids


class TestFullCharm:
    """Integration test — a well-formed charm should have minimal diagnostics."""

    def test_full_charm_minimal_issues(self, tmp_charm: pathlib.Path):
        make_full_charm(tmp_charm)
        report = lint(tmp_charm)
        # A full charm should have very few issues, if any.
        assert report.error_count == 0
        # The remaining diagnostics should only be info-level items
        # that the full charm doesn't cover (TLS, some docs topics).
        for d in report.diagnostics:
            assert d.severity != Severity.ERROR, f"Unexpected error: {d.rule_id} {d.message}"
