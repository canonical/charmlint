"""Tests for charmlint._config."""

import pathlib
import textwrap

from charmlint._config import LintConfig, load_config
from charmlint._models import Severity


class TestLintConfig:
    """Tests for LintConfig.from_dict()."""

    def test_empty_dict(self):
        config = LintConfig.from_dict({})
        assert config.severity_overrides == {}
        assert config.select == []
        assert config.ignore == []
        assert config.min_severity is None

    def test_per_rule_severity_parsed(self):
        config = LintConfig.from_dict(
            {"lint": {"per-rule-severity": {"COS005": "error", "STR002": "off"}}}
        )
        assert config.severity_overrides["COS005"] == "error"
        assert config.severity_overrides["STR002"] == "off"

    def test_select_and_ignore(self):
        config = LintConfig.from_dict(
            {"lint": {"select": ["COS", "META"], "ignore": ["STR003"]}}
        )
        assert config.select == ["COS", "META"]
        assert config.ignore == ["STR003"]

    def test_extend_select_and_extend_ignore(self):
        config = LintConfig.from_dict(
            {
                "lint": {
                    "select": ["COS"],
                    "extend-select": ["META"],
                    "ignore": ["STR003"],
                    "extend-ignore": ["DEP001"],
                }
            }
        )
        assert config.select == ["COS", "META"]
        assert config.ignore == ["STR003", "DEP001"]

    def test_severity_filter(self):
        config = LintConfig.from_dict({"severity": "warning"})
        assert config.min_severity == Severity.WARNING


class TestLoadConfig:
    """Tests for loading TOML config from disk."""

    def test_no_config_file(self, tmp_path: pathlib.Path):
        config = load_config(tmp_path)
        assert config.severity_overrides == {}

    def test_pyproject_loaded(self, tmp_path: pathlib.Path):
        (tmp_path / "pyproject.toml").write_text(
            textwrap.dedent("""
                [tool.charmlint.lint]
                ignore = ["STR002"]

                [tool.charmlint.lint.per-rule-severity]
                COS005 = "error"
            """)
        )
        config = load_config(tmp_path)
        assert config.severity_overrides["COS005"] == "error"
        assert "STR002" in config.ignore

    def test_pyproject_without_charmlint_section_ignored(self, tmp_path: pathlib.Path):
        (tmp_path / "pyproject.toml").write_text('[tool.ruff]\nline-length = 99\n')
        config = load_config(tmp_path)
        assert config == LintConfig()

    def test_standalone_charmlint_toml(self, tmp_path: pathlib.Path):
        (tmp_path / "charmlint.toml").write_text('[lint]\nselect = ["COS"]\n')
        config = load_config(tmp_path)
        assert config.select == ["COS"]

    def test_dot_charmlint_toml(self, tmp_path: pathlib.Path):
        (tmp_path / ".charmlint.toml").write_text('[lint]\nselect = ["META"]\n')
        config = load_config(tmp_path)
        assert config.select == ["META"]

    def test_standalone_preferred_over_pyproject(self, tmp_path: pathlib.Path):
        (tmp_path / "pyproject.toml").write_text(
            '[tool.charmlint.lint]\nselect = ["FROM_PYPROJECT"]\n'
        )
        (tmp_path / "charmlint.toml").write_text('[lint]\nselect = ["FROM_STANDALONE"]\n')
        config = load_config(tmp_path)
        assert config.select == ["FROM_STANDALONE"]

    def test_walks_up_parent_directories(self, tmp_path: pathlib.Path):
        (tmp_path / "charmlint.toml").write_text('[lint]\nselect = ["COS"]\n')
        nested = tmp_path / "a" / "b"
        nested.mkdir(parents=True)
        config = load_config(nested)
        assert config.select == ["COS"]

    def test_explicit_config_path_standalone(self, tmp_path: pathlib.Path):
        config_file = tmp_path / "custom.toml"
        config_file.write_text('[lint]\nselect = ["COS"]\n')
        config = load_config(tmp_path, config_path=config_file)
        assert config.select == ["COS"]

    def test_explicit_config_path_pyproject(self, tmp_path: pathlib.Path):
        config_file = tmp_path / "pyproject.toml"
        config_file.write_text('[tool.charmlint.lint]\nselect = ["COS"]\n')
        config = load_config(tmp_path, config_path=config_file)
        assert config.select == ["COS"]
