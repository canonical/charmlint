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


class TestDiscourseDocsLink:
    """Tests for METADATA-011 — documentation link still on Discourse."""

    def test_fires_with_docs_project(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "x", "links": {"documentation": "https://discourse.charmhub.io/t/x/123"}},
        )
        (tmp_charm / "docs").mkdir()
        (tmp_charm / "docs" / "conf.py").write_text('ogp_site_url = "https://x.readthedocs.io/"\n')
        report = lint(tmp_charm)
        hits = [d for d in list(report) if d.rule_id == "METADATA-011"]
        assert len(hits) == 1
        assert hits[0].severity == Severity.INFO
        assert "https://x.readthedocs.io/" in (hits[0].fix_hint or "")

    def test_fires_without_suggestion(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "x", "links": {"documentation": "https://discourse.charmhub.io/t/x/123"}},
        )
        (tmp_charm / "docs").mkdir()
        (tmp_charm / "docs" / "conf.py").write_text("project = 'x'\n")
        report = lint(tmp_charm)
        assert [d for d in list(report) if d.rule_id == "METADATA-011"]

    def test_fires_on_split_metadata(self, tmp_charm: pathlib.Path):
        # Build config in charmcraft.yaml, metadata (and so ``docs``) in
        # metadata.yaml.
        write_charmcraft_yaml(tmp_charm, {"type": "charm"})
        (tmp_charm / "metadata.yaml").write_text(
            "name: x\ndocs: https://discourse.charmhub.io/t/x/123\n"
        )
        (tmp_charm / "docs").mkdir()
        (tmp_charm / "docs" / "conf.py").write_text('ogp_site_url = "https://x.readthedocs.io/"\n')
        hits = [d for d in list(lint(tmp_charm)) if d.rule_id == "METADATA-011"]
        assert len(hits) == 1
        assert hits[0].path == "metadata.yaml"
        assert "'docs'" in hits[0].message

    def test_silent_without_docs_project(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "x", "links": {"documentation": "https://discourse.charmhub.io/t/x/123"}},
        )
        report = lint(tmp_charm)
        assert "METADATA-011" not in {d.rule_id for d in report}

    def test_silent_for_published_docs(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "x", "links": {"documentation": "https://x.readthedocs.io/"}},
        )
        (tmp_charm / "docs").mkdir()
        (tmp_charm / "docs" / "conf.py").write_text("project = 'x'\n")
        report = lint(tmp_charm)
        assert "METADATA-011" not in {d.rule_id for d in report}

    def _discourse_charm(self, charm_dir: pathlib.Path) -> None:
        write_charmcraft_yaml(
            charm_dir,
            {"name": "x", "links": {"documentation": "https://discourse.charmhub.io/t/x/123"}},
        )

    def test_noqa_on_the_link_line(self, tmp_charm: pathlib.Path):
        (tmp_charm / "charmcraft.yaml").write_text(
            "name: x\nlinks:\n"
            "  documentation: https://discourse.charmhub.io/t/x/123  # noqa: METADATA-011\n"
        )
        (tmp_charm / "docs").mkdir()
        (tmp_charm / "docs" / "conf.py").write_text("project = 'x'\n")
        assert "METADATA-011" not in {d.rule_id for d in lint(tmp_charm)}

    def test_fires_for_docs_project_at_monorepo_root(self, tmp_path: pathlib.Path):
        charm_dir = tmp_path / "repo" / "charms" / "x"
        charm_dir.mkdir(parents=True)
        (tmp_path / "repo" / ".git").mkdir()
        (tmp_path / "repo" / "docs").mkdir()
        (tmp_path / "repo" / "docs" / "conf.py").write_text("html_baseurl = 'https://x.io/'\n")
        self._discourse_charm(charm_dir)
        hits = [d for d in list(lint(charm_dir)) if d.rule_id == "METADATA-011"]
        assert len(hits) == 1
        assert "https://x.io/" in (hits[0].fix_hint or "")

    def test_ignores_docs_project_above_the_repository(self, tmp_path: pathlib.Path):
        charm_dir = tmp_path / "repo"
        charm_dir.mkdir()
        (charm_dir / ".git").mkdir()
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "conf.py").write_text("project = 'other'\n")
        self._discourse_charm(charm_dir)
        assert "METADATA-011" not in {d.rule_id for d in lint(charm_dir)}

    def test_ignores_parent_docs_project_outside_a_repository(self, tmp_charm: pathlib.Path):
        (tmp_charm.parent / "docs").mkdir()
        (tmp_charm.parent / "docs" / "conf.py").write_text("project = 'other'\n")
        self._discourse_charm(tmp_charm)
        assert "METADATA-011" not in {d.rule_id for d in lint(tmp_charm)}

    def test_list_of_links(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "x",
                "links": {
                    "documentation": [
                        "https://x.readthedocs.io/",
                        "https://discourse.charmhub.io/t/x/123",
                    ]
                },
            },
        )
        (tmp_charm / "docs").mkdir()
        (tmp_charm / "docs" / "conf.py").write_text("project = 'x'\n")
        hits = [d for d in list(lint(tmp_charm)) if d.rule_id == "METADATA-011"]
        assert len(hits) == 1
        assert "discourse" in hits[0].message

    @pytest.mark.parametrize(
        ("conf", "expected"),
        [
            (
                "ogp_site_url = 'https://x.readthedocs.io/'\nhtml_baseurl = 'https://x.io/'\n",
                "https://x.io/",
            ),
            (
                "ogp_site_url = 'https://canonical-starter-pack.readthedocs-hosted.com/'\n",
                None,
            ),
            (
                "ogp_site_url = 'https://x.io/'\n"
                "html_baseurl = os.environ.get('READTHEDOCS_CANONICAL_URL', '/')\n",
                "https://x.io/",
            ),
            # A conditional can't be read without running conf.py.
            ("html_baseurl = 'https://x.io/' if rtd else 'https://old.io/'\n", None),
            # The last assignment is the one Sphinx sees.
            (
                "html_baseurl = 'https://old.io/'\nhtml_baseurl = 'https://x.io/'\n",
                "https://x.io/",
            ),
            ("html_baseurl: str = 'https://x.io/'\n", "https://x.io/"),
            # A conf.py that doesn't parse gives no suggestion, not a crash.
            ("html_baseurl = 'https://x.io/'\nprint 'x'\n", None),
        ],
    )
    def test_suggestion(self, tmp_charm: pathlib.Path, conf: str, expected: str | None):
        self._discourse_charm(tmp_charm)
        (tmp_charm / "docs").mkdir()
        (tmp_charm / "docs" / "conf.py").write_text(conf)
        [hit] = [d for d in list(lint(tmp_charm)) if d.rule_id == "METADATA-011"]
        if expected:
            assert expected in (hit.fix_hint or "")
        else:
            assert "published URL" in (hit.fix_hint or "")
