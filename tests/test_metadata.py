"""Tests for METADATA rules."""

import pathlib

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
