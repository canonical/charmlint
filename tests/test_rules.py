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


class TestFullCharm:
    """Integration test — a well-formed charm should have minimal diagnostics."""

    def test_full_charm_minimal_issues(self, tmp_charm: pathlib.Path):
        make_full_charm(tmp_charm)
        report = lint(tmp_charm)
        assert report.error_count == 0
        for d in report.diagnostics:
            assert d.severity != Severity.ERROR, f"Unexpected error: {d.rule_id} {d.message}"
