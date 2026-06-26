"""Tests for CC005/CC006 — unknown field detection in charmcraft.yaml."""

import pathlib

from charmlint._linter import lint
from tests.conftest import write_charmcraft_yaml


class TestUnknownTopLevelFields:
    """Tests for CC005 — unrecognised top-level keys."""

    def test_known_fields_clean(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "type": "charm",
                "summary": "A test charm",
                "description": "Longer description.",
                "base": "ubuntu@24.04",
                "platforms": {"amd64": None},
                "parts": {"charm": {"plugin": "uv"}},
                "requires": {"db": {"interface": "postgresql"}},
                "provides": {"metrics": {"interface": "prometheus_scrape"}},
                "peers": {"cluster": {"interface": "cluster"}},
                "config": {"options": {"port": {"type": "int"}}},
                "actions": {"backup": {"description": "Run backup"}},
                "containers": {"app": {"resource": "app-image"}},
                "resources": {"app-image": {"type": "oci-image"}},
                "storage": {"data": {"type": "filesystem"}},
                "assumes": ["juju >= 3.1"],
                "subordinate": False,
                "charm-libs": [],
                "links": {"documentation": "https://example.com"},
                "extra-bindings": {"admin": {}},
            },
        )
        report = lint(tmp_charm)
        assert "CC005" not in {d.rule_id for d in report.diagnostics}

    def test_typo_detected(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test", "sumary": "oops"})
        report = lint(tmp_charm)
        cc005 = [d for d in report.diagnostics if d.rule_id == "CC005"]
        assert len(cc005) == 1
        assert "sumary" in cc005[0].message

    def test_typo_fix_hint(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test", "sumary": "oops"})
        report = lint(tmp_charm)
        cc005 = [d for d in report.diagnostics if d.rule_id == "CC005"]
        assert cc005[0].fix_hint is not None
        assert "summary" in cc005[0].fix_hint

    def test_multiple_unknown(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "sumary": "oops",
                "descrption": "also oops",
            },
        )
        report = lint(tmp_charm)
        cc005 = [d for d in report.diagnostics if d.rule_id == "CC005"]
        assert len(cc005) == 2
        messages = " ".join(d.message for d in cc005)
        assert "sumary" in messages
        assert "descrption" in messages

    def test_completely_unknown_no_hint(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test", "zzz-nonsense": "value"})
        report = lint(tmp_charm)
        cc005 = [d for d in report.diagnostics if d.rule_id == "CC005"]
        assert len(cc005) == 1
        assert cc005[0].fix_hint is None

    def test_legacy_fields_accepted(self, tmp_charm: pathlib.Path):
        """Legacy fields like 'series' and 'min-juju-version' should not trigger CC005."""
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "series": ["focal"],
                "min-juju-version": "2.9",
            },
        )
        report = lint(tmp_charm)
        # CC001 may fire for deprecated series, but CC005 should not.
        assert "CC005" not in {d.rule_id for d in report.diagnostics}

    def test_cc005_path_is_charmcraft_yaml(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test", "sumary": "oops"})
        report = lint(tmp_charm)
        cc005 = [d for d in report.diagnostics if d.rule_id == "CC005"]
        assert cc005[0].path == "charmcraft.yaml"

    def test_cc005_path_is_metadata_yaml_for_legacy_charms(self, tmp_charm: pathlib.Path):
        (tmp_charm / "metadata.yaml").write_text("name: test\nsumary: oops\n")
        report = lint(tmp_charm)
        cc005 = [d for d in report.diagnostics if d.rule_id == "CC005"]
        assert len(cc005) == 1
        assert cc005[0].path == "metadata.yaml"

    def test_metadata_yaml_specific_fields_not_flagged(self, tmp_charm: pathlib.Path):
        """Fields valid in metadata.yaml but not charmcraft.yaml must not trigger CC005."""
        (tmp_charm / "metadata.yaml").write_text(
            "name: test\n"
            "display-name: My Charm\n"
            "maintainers:\n  - foo@example.com\n"
            "docs: https://example.com/docs\n"
            "issues: https://example.com/issues\n"
            "source: https://example.com/source\n"
            "website: https://example.com\n"
        )
        report = lint(tmp_charm)
        assert "CC005" not in {d.rule_id for d in report.diagnostics}

    def test_charmcraft_only_fields_flagged_in_metadata_yaml(self, tmp_charm: pathlib.Path):
        """charmcraft.yaml-only fields (parts, charm-libs, links) must be flagged in metadata.yaml."""
        (tmp_charm / "metadata.yaml").write_text("name: test\nparts:\n  charm:\n    plugin: uv\n")
        report = lint(tmp_charm)
        cc005 = [d for d in report.diagnostics if d.rule_id == "CC005"]
        assert len(cc005) == 1
        assert "parts" in cc005[0].message

    def test_metadata_yaml_fields_flagged_in_charmcraft_yaml(self, tmp_charm: pathlib.Path):
        """metadata.yaml-only fields (display-name, maintainers) must be flagged in charmcraft.yaml."""
        write_charmcraft_yaml(tmp_charm, {"name": "test", "display-name": "My Charm"})
        report = lint(tmp_charm)
        cc005 = [d for d in report.diagnostics if d.rule_id == "CC005"]
        assert len(cc005) == 1
        assert "display-name" in cc005[0].message
        assert cc005[0].path == "charmcraft.yaml"

    def test_maintainers_flagged_in_charmcraft_yaml(self, tmp_charm: pathlib.Path):
        """'maintainers' is valid in metadata.yaml but must be flagged in charmcraft.yaml (use links.contact instead)."""
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "test", "maintainers": ["foo@example.com"]},
        )
        report = lint(tmp_charm)
        cc005 = [d for d in report.diagnostics if d.rule_id == "CC005"]
        assert len(cc005) == 1
        assert "maintainers" in cc005[0].message
        assert cc005[0].path == "charmcraft.yaml"


class TestUnknownResourceFields:
    """Tests for CC006 — unrecognised keys in resource definitions."""

    def test_valid_resource_fields(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "resources": {
                    "app-image": {
                        "type": "oci-image",
                        "description": "App image",
                    },
                    "tarball": {
                        "type": "file",
                        "filename": "app.tar.gz",
                        "description": "Source tarball",
                        "upstream-source": "https://example.com/app.tar.gz",
                    },
                },
            },
        )
        report = lint(tmp_charm)
        assert "CC006" not in {d.rule_id for d in report.diagnostics}

    def test_typo_in_resource(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "resources": {
                    "app-image": {
                        "type": "oci-image",
                        "descrption": "App image",
                    },
                },
            },
        )
        report = lint(tmp_charm)
        cc006 = [d for d in report.diagnostics if d.rule_id == "CC006"]
        assert len(cc006) == 1
        assert "descrption" in cc006[0].message
        assert "app-image" in cc006[0].message

    def test_resource_fix_hint(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "resources": {
                    "img": {"type": "oci-image", "descrption": "typo"},
                },
            },
        )
        report = lint(tmp_charm)
        cc006 = [d for d in report.diagnostics if d.rule_id == "CC006"]
        assert cc006[0].fix_hint is not None
        assert "description" in cc006[0].fix_hint

    def test_no_resources_section(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        report = lint(tmp_charm)
        assert "CC006" not in {d.rule_id for d in report.diagnostics}

    def test_non_dict_resource_ignored(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "resources": {"img": "not-a-dict"},
            },
        )
        report = lint(tmp_charm)
        assert "CC006" not in {d.rule_id for d in report.diagnostics}
