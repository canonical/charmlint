"""Tests for charmlint.config."""

import pathlib

import yaml

from charmlint.config import LintConfig, load_config
from charmlint.models import Severity


class TestLintConfig:
    """Tests for LintConfig.from_dict()."""

    def test_empty_dict(self):
        config = LintConfig.from_dict({})
        assert config.severity_overrides == {}
        assert config.select == []
        assert config.ignore == []
        assert config.min_severity is None

    def test_rules_parsed(self):
        config = LintConfig.from_dict({"rules": {"COS005": "error", "STR002": "off"}})
        assert config.severity_overrides["COS005"] == "error"
        assert config.severity_overrides["STR002"] == "off"

    def test_select_and_ignore(self):
        config = LintConfig.from_dict({"select": ["COS", "META"], "ignore": ["STR003"]})
        assert config.select == ["COS", "META"]
        assert config.ignore == ["STR003"]

    def test_severity_filter(self):
        config = LintConfig.from_dict({"severity": "warning"})
        assert config.min_severity == Severity.WARNING


class TestLoadConfig:
    """Tests for loading .charmlint.yaml from disk."""

    def test_no_config_file(self, tmp_path: pathlib.Path):
        config = load_config(tmp_path)
        assert config.severity_overrides == {}

    def test_config_file_loaded(self, tmp_path: pathlib.Path):
        config_data = {
            "rules": {"COS005": "error"},
            "ignore": ["STR002"],
        }
        with (tmp_path / ".charmlint.yaml").open("w") as f:
            yaml.dump(config_data, f)

        config = load_config(tmp_path)
        assert config.severity_overrides["COS005"] == "error"
        assert "STR002" in config.ignore

    def test_explicit_config_path(self, tmp_path: pathlib.Path):
        config_file = tmp_path / "custom.yaml"
        with config_file.open("w") as f:
            yaml.dump({"select": ["COS"]}, f)

        config = load_config(tmp_path, config_path=config_file)
        assert config.select == ["COS"]
