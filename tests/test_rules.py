"""Tests for charmlint rules.

Only METADATA-relevant tests live here during the rules-refactor; the
other rule families are re-added alongside their PRs from
``RULES_TRACKER.md``.
"""

import pathlib
import urllib.error
import urllib.request

import pytest

from charmlint._linter import lint
from charmlint._models import Severity
from charmlint._rules._base import get_all_rules
from tests.conftest import make_full_charm, write_charmcraft_yaml

_RULES_WITH_URL = sorted(
    (r for r in get_all_rules().values() if r.reference_url is not None),
    key=lambda r: r.id,
)


class TestMetadataRules:
    """Tests for metadata field checks."""

    def test_missing_name_is_error(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"display-name": "X"})
        report = lint(tmp_charm)
        ids = {d.rule_id for d in list(report)}
        assert "METADATA-001" in ids
        meta001 = [d for d in list(report) if d.rule_id == "METADATA-001"][0]
        assert meta001.severity == Severity.ERROR

    def test_full_metadata_no_meta_diagnostics(self, tmp_charm: pathlib.Path):
        make_full_charm(tmp_charm)
        report = lint(tmp_charm)
        meta_ids = {d.rule_id for d in list(report) if d.rule_id.startswith("METADATA")}
        assert not meta_ids

    def test_meta_diagnostics_path_is_charmcraft_yaml(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"display-name": "X"})
        report = lint(tmp_charm)
        meta001 = [d for d in list(report) if d.rule_id == "METADATA-001"][0]
        assert meta001.path == "charmcraft.yaml"

    def test_meta_diagnostics_path_is_metadata_yaml_for_legacy_charms(
        self, tmp_charm: pathlib.Path
    ):
        (tmp_charm / "metadata.yaml").write_text("display-name: X\n")
        report = lint(tmp_charm)
        meta001 = [d for d in list(report) if d.rule_id == "METADATA-001"][0]
        assert meta001.path == "metadata.yaml"

    def test_bare_metadata_fires_all_completeness_rules(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test-charm"})
        report = lint(tmp_charm)
        ids = {d.rule_id for d in list(report)}
        for rid in (
            "METADATA-002",
            "METADATA-003",
            "METADATA-004",
            "METADATA-005",
            "METADATA-006",
            "METADATA-007",
        ):
            assert rid in ids, f"{rid} should fire when the field is missing"

    def test_legacy_fields_in_charmcraft_yaml_do_not_satisfy_meta(self, tmp_charm: pathlib.Path):
        # Legacy metadata.yaml key names in charmcraft.yaml are the wrong spelling
        # for that file — the checks should still fire even though the info is
        # technically present.
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test-charm",
                "display-name": "Test Charm",
                "summary": "x",
                "description": "x",
                "docs": "https://example.com/docs",
                "issues": "https://example.com/issues",
                "source": "https://example.com/source",
            },
        )
        report = lint(tmp_charm)
        ids = {d.rule_id for d in list(report)}
        for rid in ("METADATA-002", "METADATA-005", "METADATA-006", "METADATA-007"):
            assert rid in ids, f"{rid} should fire — key belongs in metadata.yaml, not here"
        for rid in ("METADATA-003", "METADATA-004"):
            assert rid not in ids, f"{rid} accepts the same key in both files"

    def test_modern_fields_in_metadata_yaml_do_not_satisfy_meta(self, tmp_charm: pathlib.Path):
        # Modern charmcraft.yaml key names in metadata.yaml are the wrong spelling
        # for that file — the checks should still fire.
        (tmp_charm / "metadata.yaml").write_text(
            "name: test-charm\n"
            "title: Test Charm\n"
            "summary: x\n"
            "description: x\n"
            "links:\n"
            "  documentation: https://example.com/docs\n"
            "  issues: https://example.com/issues\n"
            "  source: https://example.com/source\n"
        )
        report = lint(tmp_charm)
        ids = {d.rule_id for d in list(report)}
        for rid in ("METADATA-002", "METADATA-005", "METADATA-006", "METADATA-007"):
            assert rid in ids, f"{rid} should fire — key belongs in charmcraft.yaml, not here"

    def test_legacy_fields_in_metadata_yaml_satisfy_meta(self, tmp_charm: pathlib.Path):
        (tmp_charm / "metadata.yaml").write_text(
            "name: test-charm\n"
            "display-name: Test Charm\n"
            "summary: x\n"
            "description: x\n"
            "docs: https://example.com/docs\n"
            "issues: https://example.com/issues\n"
            "source: https://example.com/source\n"
        )
        report = lint(tmp_charm)
        ids = {d.rule_id for d in list(report)}
        for rid in (
            "METADATA-002",
            "METADATA-003",
            "METADATA-004",
            "METADATA-005",
            "METADATA-006",
            "METADATA-007",
        ):
            assert rid not in ids, f"{rid} should not fire for legacy metadata.yaml fields"

    def test_modern_charmcraft_title_and_links_satisfy_meta(self, tmp_charm: pathlib.Path):
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
        ids = {d.rule_id for d in list(report)}
        for rid in (
            "METADATA-002",
            "METADATA-005",
            "METADATA-006",
            "METADATA-007",
        ):
            assert rid not in ids, f"{rid} should not fire for modern charmcraft.yaml"

    def test_bundle_skips_metadata_rules(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"type": "bundle", "name": "my-bundle"})
        report = lint(tmp_charm)
        meta_ids = {d.rule_id for d in list(report) if d.rule_id.startswith("METADATA")}
        assert not meta_ids

    def test_legacy_bundle_yaml_skips_metadata_rules(self, tmp_charm: pathlib.Path):
        (tmp_charm / "bundle.yaml").write_text("applications: {}\n")
        write_charmcraft_yaml(tmp_charm, {})
        report = lint(tmp_charm)
        meta_ids = {d.rule_id for d in list(report) if d.rule_id.startswith("METADATA")}
        assert not meta_ids


class TestDocumentationRules:
    """Tests for documentation presence rules."""

    def test_no_readme(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        report = lint(tmp_charm)
        assert "DOCUMENTATION-001" in {d.rule_id for d in report}

    @pytest.mark.parametrize(
        "filename",
        ["README.md", "README.txt", "README.rst", "readme.md", "Readme.MD", "README.RST"],
    )
    def test_readme_present(self, tmp_charm: pathlib.Path, filename: str):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        (tmp_charm / filename).write_text("# Hello\n")
        report = lint(tmp_charm)
        assert "DOCUMENTATION-001" not in {d.rule_id for d in report}

    @pytest.mark.parametrize("filename", ["README.org", "README", "README.markdown"])
    def test_readme_unsupported_extension(self, tmp_charm: pathlib.Path, filename: str):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        (tmp_charm / filename).write_text("# Hello\n")
        report = lint(tmp_charm)
        assert "DOCUMENTATION-001" in {d.rule_id for d in report}


class TestReferenceUrls:
    """Every rule with a reference_url must point somewhere live."""

    @pytest.mark.parametrize("rule", _RULES_WITH_URL, ids=lambda r: r.id)
    def test_reference_url_resolves(self, rule):
        assert rule.reference_url is not None
        request = urllib.request.Request(rule.reference_url, method="HEAD")
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                status = response.status
        except urllib.error.HTTPError as exc:
            if exc.code == 405:
                # HEAD not allowed — retry with GET.
                with urllib.request.urlopen(rule.reference_url, timeout=10) as response:
                    status = response.status
            else:
                raise
        assert 200 <= status < 300, f"{rule.id}: {rule.reference_url} → HTTP {status}"


class TestTestingRules:
    """Tests for TESTING-001 — no unit tests found."""

    def test_no_unit_tests_is_warning(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test-charm"})
        report = lint(tmp_charm)
        testing = [d for d in list(report) if d.rule_id == "TESTING-001"]
        assert len(testing) == 1
        assert testing[0].severity == Severity.WARNING
        assert testing[0].path == "tests/unit/"

    def test_unit_tests_present_no_diagnostic(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test-charm"})
        (tmp_charm / "tests" / "unit").mkdir(parents=True)
        (tmp_charm / "tests" / "unit" / "test_charm.py").write_text("def test_x(): pass\n")
        report = lint(tmp_charm)
        assert "TESTING-001" not in {d.rule_id for d in list(report)}

    def test_reactive_unit_tests_layout_no_diagnostic(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test-charm"})
        (tmp_charm / "unit_tests").mkdir()
        (tmp_charm / "unit_tests" / "test_charm.py").write_text("def test_x(): pass\n")
        report = lint(tmp_charm)
        assert "TESTING-001" not in {d.rule_id for d in list(report)}

    def test_nested_unit_tests_no_diagnostic(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test-charm"})
        nested = tmp_charm / "tests" / "unit" / "test_workload"
        nested.mkdir(parents=True)
        (nested / "test_thing.py").write_text("def test_x(): pass\n")
        report = lint(tmp_charm)
        assert "TESTING-001" not in {d.rule_id for d in list(report)}


class TestFullCharm:
    """Integration test — a well-formed charm should have minimal diagnostics."""

    def test_full_charm_minimal_issues(self, tmp_charm: pathlib.Path):
        make_full_charm(tmp_charm)
        report = lint(tmp_charm)
        assert report.error_count == 0
        for d in list(report):
            assert d.severity != Severity.ERROR, f"Unexpected error: {d.rule_id} {d.message}"
