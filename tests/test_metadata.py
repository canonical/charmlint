"""Tests for METADATA rules."""

import pathlib

import pytest

from charmlint._linter import lint
from charmlint._models import Severity
from tests.conftest import write_charmcraft_yaml


class TestRequiresMissingOptional:
    """Tests for METADATA-008 — `requires` endpoint missing `optional`."""

    def test_missing_optional_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "x", "requires": {"db": {"interface": "postgresql"}}},
        )
        report = lint(tmp_charm)
        hits = [d for d in list(report) if d.rule_id == "METADATA-008"]
        assert len(hits) == 1
        assert hits[0].severity == Severity.INFO
        assert "db" in hits[0].message

    def test_optional_true_suppresses(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "x",
                "requires": {"db": {"interface": "postgresql", "optional": True}},
            },
        )
        report = lint(tmp_charm)
        assert not [d for d in list(report) if d.rule_id == "METADATA-008"]

    def test_optional_false_suppresses(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "x",
                "requires": {"db": {"interface": "postgresql", "optional": False}},
            },
        )
        report = lint(tmp_charm)
        assert not [d for d in list(report) if d.rule_id == "METADATA-008"]

    def test_no_requires_section_not_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        report = lint(tmp_charm)
        assert not [d for d in list(report) if d.rule_id == "METADATA-008"]

    def test_multiple_endpoints_reported_independently(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "x",
                "requires": {
                    "db": {"interface": "postgresql"},
                    "cache": {"interface": "redis", "optional": True},
                    "logs": {"interface": "loki"},
                },
            },
        )
        report = lint(tmp_charm)
        hits = sorted(d.message for d in list(report) if d.rule_id == "METADATA-008")
        assert len(hits) == 2
        assert any("db" in m for m in hits)
        assert any("logs" in m for m in hits)

    def test_provides_missing_optional_does_not_fire_requires_rule(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "x", "provides": {"metrics": {"interface": "prometheus_scrape"}}},
        )
        report = lint(tmp_charm)
        assert not [d for d in list(report) if d.rule_id == "METADATA-008"]


class TestProvidesMissingOptional:
    """Tests for METADATA-009 — `provides` endpoint missing `optional`."""

    def test_missing_optional_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "x", "provides": {"metrics": {"interface": "prometheus_scrape"}}},
        )
        report = lint(tmp_charm)
        hits = [d for d in list(report) if d.rule_id == "METADATA-009"]
        assert len(hits) == 1
        assert hits[0].severity == Severity.INFO
        assert "metrics" in hits[0].message

    def test_optional_true_suppresses(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "x",
                "provides": {"metrics": {"interface": "prometheus_scrape", "optional": True}},
            },
        )
        report = lint(tmp_charm)
        assert not [d for d in list(report) if d.rule_id == "METADATA-009"]

    def test_optional_false_suppresses(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "x",
                "provides": {"metrics": {"interface": "prometheus_scrape", "optional": False}},
            },
        )
        report = lint(tmp_charm)
        assert not [d for d in list(report) if d.rule_id == "METADATA-009"]

    def test_no_provides_section_not_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        report = lint(tmp_charm)
        assert not [d for d in list(report) if d.rule_id == "METADATA-009"]

    def test_multiple_endpoints_reported_independently(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "x",
                "provides": {
                    "metrics": {"interface": "prometheus_scrape"},
                    "dashboard": {"interface": "grafana_dashboard", "optional": True},
                    "logs": {"interface": "loki_push_api"},
                },
            },
        )
        report = lint(tmp_charm)
        hits = sorted(d.message for d in list(report) if d.rule_id == "METADATA-009")
        assert len(hits) == 2
        assert any("metrics" in m for m in hits)
        assert any("logs" in m for m in hits)

    def test_requires_missing_optional_does_not_fire_provides_rule(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "x", "requires": {"db": {"interface": "postgresql"}}},
        )
        report = lint(tmp_charm)
        assert not [d for d in list(report) if d.rule_id == "METADATA-009"]


@pytest.mark.parametrize(
    ("rule_id", "section"), [("METADATA-008", "requires"), ("METADATA-009", "provides")]
)
class TestMissingOptionalIsAnchored:
    """METADATA-008/009 point at the endpoint, so a directive there silences them."""

    def test_anchored_to_the_endpoint_line(
        self, tmp_charm: pathlib.Path, rule_id: str, section: str
    ):
        (tmp_charm / "charmcraft.yaml").write_text(
            f"name: x\n{section}:\n  first:\n    interface: a\n  second:\n    interface: b\n"
        )
        found = {d.line for d in lint(tmp_charm) if d.rule_id == rule_id}
        assert found == {3, 5}

    def test_ignore_on_the_endpoint_line_suppresses(
        self, tmp_charm: pathlib.Path, rule_id: str, section: str
    ):
        (tmp_charm / "charmcraft.yaml").write_text(
            f"name: x\n{section}:\n"
            f"  first:  # charmlint: ignore[{rule_id}]\n    interface: a\n"
            "  second:\n    interface: b\n"
        )
        assert [d.line for d in lint(tmp_charm) if d.rule_id == rule_id] == [5]


class TestCircularWebsiteLink:
    """Tests for METADATA-010 — `website` link to the charm's own Charmhub page."""

    @pytest.mark.parametrize(
        "website",
        [
            "https://charmhub.io/test-charm",
            "http://charmhub.io/test-charm",
            "https://charmhub.io/test-charm/",
            "https://www.charmhub.io/test-charm",
            "charmhub.io/test-charm",
            "https://charmhub.io/test-charm?channel=edge",
        ],
    )
    def test_circular_website_link_fires(self, tmp_charm: pathlib.Path, website: str):
        write_charmcraft_yaml(tmp_charm, {"name": "test-charm", "links": {"website": website}})
        report = lint(tmp_charm)
        meta010 = [d for d in list(report) if d.rule_id == "METADATA-010"]
        assert meta010, f"METADATA-010 should fire for {website}"
        assert meta010[0].severity == Severity.INFO
        assert meta010[0].path == "charmcraft.yaml"

    @pytest.mark.parametrize(
        "website",
        [
            "https://example.com/test-charm",
            "https://charmhub.io/other-charm",
            # Sub-pages carry content the landing page does not, so they are a
            # deliberate destination rather than a circular link.
            "https://charmhub.io/test-charm/docs",
            "https://charmhub.io",
            "https://notcharmhub.io/test-charm",
            "ftp://charmhub.io/test-charm",
            # Unparseable URLs are somebody else's problem, not a circular link.
            "http://[::1/test-charm",
        ],
    )
    def test_circular_website_link_does_not_fire(self, tmp_charm: pathlib.Path, website: str):
        write_charmcraft_yaml(tmp_charm, {"name": "test-charm", "links": {"website": website}})
        report = lint(tmp_charm)
        assert "METADATA-010" not in {d.rule_id for d in report}, f"should not fire for {website}"

    def test_circular_website_link_in_list(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test-charm",
                "links": {"website": ["https://example.com", "https://charmhub.io/test-charm"]},
            },
        )
        report = lint(tmp_charm)
        meta010 = [d for d in list(report) if d.rule_id == "METADATA-010"]
        assert len(meta010) == 1
        assert "https://charmhub.io/test-charm" in meta010[0].message

    def test_listed_link_anchors_to_its_own_line(self, tmp_charm: pathlib.Path):
        # The offending entry, not the `website:` key above it — so the line
        # a reader is sent to is the line they have to edit.
        (tmp_charm / "charmcraft.yaml").write_text(
            "name: test-charm\n"
            "links:\n"
            "  website:\n"
            "    - https://example.com\n"
            "    - https://charmhub.io/test-charm\n"
        )
        report = lint(tmp_charm)
        meta010 = [d for d in list(report) if d.rule_id == "METADATA-010"]
        assert len(meta010) == 1
        assert meta010[0].line == 5

    def test_noqa_beside_one_listed_link_silences_only_that_one(self, tmp_charm: pathlib.Path):
        (tmp_charm / "charmcraft.yaml").write_text(
            "name: test-charm\n"
            "links:\n"
            "  website:\n"
            "    - https://charmhub.io/test-charm  # noqa\n"
            "    - https://www.charmhub.io/test-charm\n"
        )
        report = lint(tmp_charm)
        meta010 = [d for d in list(report) if d.rule_id == "METADATA-010"]
        assert len(meta010) == 1
        assert meta010[0].line == 5

    def test_circular_website_link_legacy_metadata_yaml(self, tmp_charm: pathlib.Path):
        (tmp_charm / "metadata.yaml").write_text(
            "name: test-charm\nwebsite: https://charmhub.io/test-charm\n"
        )
        report = lint(tmp_charm)
        meta010 = [d for d in list(report) if d.rule_id == "METADATA-010"]
        assert len(meta010) == 1
        assert meta010[0].path == "metadata.yaml"
        assert meta010[0].line == 2

    def test_circular_website_link_split_metadata(self, tmp_charm: pathlib.Path):
        # Charms that keep charmcraft.yaml and metadata.yaml side by side spell
        # the field the metadata.yaml way, and it should still be caught.
        write_charmcraft_yaml(tmp_charm, {"type": "charm"})
        (tmp_charm / "metadata.yaml").write_text(
            "name: test-charm\nwebsite: https://charmhub.io/test-charm\n"
        )
        report = lint(tmp_charm)
        meta010 = [d for d in list(report) if d.rule_id == "METADATA-010"]
        assert len(meta010) == 1
        assert meta010[0].path == "metadata.yaml"

    def test_circular_website_link_wrong_spelling_for_file(self, tmp_charm: pathlib.Path):
        # `website` at the top level belongs in metadata.yaml; in
        # charmcraft.yaml it is a misplaced field, which CHARMCRAFT-004 reports.
        write_charmcraft_yaml(
            tmp_charm, {"name": "test-charm", "website": "https://charmhub.io/test-charm"}
        )
        report = lint(tmp_charm)
        assert "METADATA-010" not in {d.rule_id for d in report}

    def test_circular_website_link_needs_a_name(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"links": {"website": "https://charmhub.io/test-charm"}})
        report = lint(tmp_charm)
        assert "METADATA-010" not in {d.rule_id for d in report}
