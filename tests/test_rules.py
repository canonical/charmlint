"""Tests for charmlint rules.

Only METADATA-relevant tests live here during the rules-refactor; the
other rule families are re-added alongside their PRs from
``RULES_TRACKER.md``.
"""

import collections
import pathlib
import time
import urllib.error
import urllib.parse
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


def _rules_by_page() -> dict[str, list[str]]:
    """Map each distinct page to the rules citing it.

    A `#fragment` never reaches the server, so several rules pointing at
    different anchors of one page are a single request. Collapsing them
    keeps the suite from hammering the same host once per rule.
    """
    pages: dict[str, list[str]] = collections.defaultdict(list)
    for rule in _RULES_WITH_URL:
        assert rule.reference_url is not None
        page, _ = urllib.parse.urldefrag(rule.reference_url)
        pages[page].append(rule.id)
    return dict(pages)


_REFERENCE_PAGES = sorted(_rules_by_page().items())


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


# A documentation host may throttle or hiccup; that is not a broken
# reference. Only a settled non-2xx answer counts as a failure.
_TRANSIENT_CODES = frozenset({408, 429, 500, 502, 503, 504})


def _fetch_status(url: str) -> int:
    """Return the HTTP status for *url*, retrying transient answers."""
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status
        except urllib.error.HTTPError as exc:
            if exc.code == 405:
                # HEAD not allowed — retry with GET.
                with urllib.request.urlopen(url, timeout=10) as response:
                    return response.status
            if exc.code not in _TRANSIENT_CODES or attempt == 2:
                raise
        except urllib.error.URLError:
            if attempt == 2:
                raise
        time.sleep(2**attempt)
    raise AssertionError("unreachable")


class TestReferenceUrls:
    """Every rule with a reference_url must point somewhere live."""

    @pytest.mark.parametrize(("page", "rule_ids"), _REFERENCE_PAGES, ids=lambda v: v)
    def test_reference_url_resolves(self, page: str, rule_ids: list[str]):
        status = _fetch_status(page)
        cited_by = ", ".join(rule_ids)
        assert 200 <= status < 300, f"{cited_by}: {page} → HTTP {status}"


class TestStructureRules:
    """Tests for structure rules."""

    def test_no_licence(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        report = lint(tmp_charm)
        assert "STRUCTURE-001" in {d.rule_id for d in report}

    @pytest.mark.parametrize("name", ["LICENSE", "LICENCE"])
    def test_licence_present_no_diagnostic(self, tmp_charm: pathlib.Path, name: str):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        (tmp_charm / name).write_text("Apache-2.0\n")
        report = lint(tmp_charm)
        assert "STRUCTURE-001" not in {d.rule_id for d in report}

    def test_both_licence_spellings_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        (tmp_charm / "LICENSE").write_text("Apache-2.0\n")
        (tmp_charm / "LICENCE").write_text("Apache-2.0\n")
        report = lint(tmp_charm)
        str001 = [d for d in report if d.rule_id == "STRUCTURE-001"]
        assert len(str001) == 1
        assert "both" in str001[0].message.lower()

    def test_empty_licence_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        (tmp_charm / "LICENSE").write_text("")
        report = lint(tmp_charm)
        assert "STRUCTURE-001" in {d.rule_id for d in report}

    def test_licence_directory_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        (tmp_charm / "LICENSE").mkdir()
        report = lint(tmp_charm)
        assert "STRUCTURE-001" in {d.rule_id for d in report}

    def test_no_icon(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        report = lint(tmp_charm)
        assert "STRUCTURE-002" in {d.rule_id for d in report}

    def test_icon_present_no_diagnostic(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        (tmp_charm / "icon.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"/>\n')
        report = lint(tmp_charm)
        assert "STRUCTURE-002" not in {d.rule_id for d in report}

    def test_empty_icon_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        (tmp_charm / "icon.svg").write_text("")
        report = lint(tmp_charm)
        assert "STRUCTURE-002" in {d.rule_id for d in report}

    def test_icon_directory_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        (tmp_charm / "icon.svg").mkdir()
        report = lint(tmp_charm)
        assert "STRUCTURE-002" in {d.rule_id for d in report}


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


def _vendor_lib(charm_dir: pathlib.Path, owner: str, version: str, lib: str) -> pathlib.Path:
    """Simulate ``charmcraft fetch-lib`` by dropping a stub into lib/charms/."""
    lib_dir = charm_dir / "lib" / "charms" / owner / version
    lib_dir.mkdir(parents=True)
    path = lib_dir / f"{lib}.py"
    path.write_text('"""stub"""\n')
    return path


class TestLibraryRules:
    """Tests for vendored charm-library detection."""

    @pytest.mark.parametrize(
        ("owner", "version", "lib", "expected_pkg"),
        [
            (
                "tls_certificates_interface",
                "v3",
                "tls_certificates",
                "charmlibs-interfaces-tls-certificates",
            ),
            ("hydra", "v0", "oauth", "charmlibs-interfaces-oauth"),
            ("traefik_k8s", "v2", "forward_auth", "charmlibs-interfaces-forward-auth"),
            ("openfga_k8s", "v1", "openfga", "charmlibs-interfaces-openfga"),
            ("istio_beacon_k8s", "v0", "service_mesh", "charmlibs-interfaces-service-mesh"),
        ],
    )
    def test_interface_libs_flagged(
        self,
        tmp_charm: pathlib.Path,
        owner: str,
        version: str,
        lib: str,
        expected_pkg: str,
    ):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        lib_path = _vendor_lib(tmp_charm, owner, version, lib)
        report = lint(tmp_charm)
        lib001 = [d for d in report if d.rule_id == "LIBRARY-001"]
        assert len(lib001) == 1
        assert expected_pkg in lib001[0].message
        assert lib001[0].severity == Severity.WARNING
        assert lib001[0].path == lib_path.relative_to(tmp_charm).as_posix()
        assert lib001[0].fix_hint is not None
        assert f"uv add {expected_pkg}" in lib001[0].fix_hint

    def test_operator_libs_linux_submodule_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        _vendor_lib(tmp_charm, "operator_libs_linux", "v0", "apt")
        report = lint(tmp_charm)
        lib001 = [d for d in report if d.rule_id == "LIBRARY-001"]
        assert len(lib001) == 1
        assert "charmlibs-apt" in lib001[0].message

    def test_general_lib_flagged_regardless_of_owner(self, tmp_charm: pathlib.Path):
        # rollingops ships under the rolling_ops charm, not operator_libs_linux,
        # so it exercises the owner-agnostic general mapping.
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        _vendor_lib(tmp_charm, "rolling_ops", "v0", "rollingops")
        report = lint(tmp_charm)
        lib001 = [d for d in report if d.rule_id == "LIBRARY-001"]
        assert len(lib001) == 1
        assert "charmlibs-rollingops" in lib001[0].message

    def test_unknown_operator_libs_linux_submodule_not_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        _vendor_lib(tmp_charm, "operator_libs_linux", "v0", "notreal")
        report = lint(tmp_charm)
        assert "LIBRARY-001" not in {d.rule_id for d in report}

    def test_unmapped_charm_lib_not_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        _vendor_lib(tmp_charm, "some_random_charm", "v0", "some_lib")
        report = lint(tmp_charm)
        assert "LIBRARY-001" not in {d.rule_id for d in report}

    def test_multiple_versions_reported_separately(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        _vendor_lib(tmp_charm, "operator_libs_linux", "v0", "apt")
        _vendor_lib(tmp_charm, "operator_libs_linux", "v1", "apt")
        report = lint(tmp_charm)
        assert len([d for d in report if d.rule_id == "LIBRARY-001"]) == 2

    def test_no_lib_dir_no_diagnostics(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        report = lint(tmp_charm)
        assert "LIBRARY-001" not in {d.rule_id for d in report}


class TestFullCharm:
    """Integration test — a well-formed charm should have minimal diagnostics."""

    def test_full_charm_minimal_issues(self, tmp_charm: pathlib.Path):
        make_full_charm(tmp_charm)
        report = lint(tmp_charm)
        assert report.error_count == 0
        for d in list(report):
            assert d.severity != Severity.ERROR, f"Unexpected error: {d.rule_id} {d.message}"
