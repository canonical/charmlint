"""Tests for charmlint._config."""

import pathlib
import re
import textwrap

import pytest

from charmlint._config import ConfigError, LintConfig, load_config
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
            {"per-rule-severity": {"SECURITY-001": "error", "STRUCTURE-002": "warning"}}
        )
        assert config.severity_overrides["SECURITY-001"] == "error"
        assert config.severity_overrides["STRUCTURE-002"] == "warning"

    def test_select_and_ignore(self):
        config = LintConfig.from_dict(
            {"select": ["SECURITY", "METADATA"], "ignore": ["CONFIG-003"]}
        )
        assert config.select == ["SECURITY", "METADATA"]
        assert config.ignore == ["CONFIG-003"]

    def test_extend_select_and_extend_ignore(self):
        config = LintConfig.from_dict(
            {
                "select": ["SECURITY"],
                "extend-select": ["METADATA"],
                "ignore": ["CONFIG-003"],
                "extend-ignore": ["LIBRARY-001"],
            }
        )
        assert config.select == ["SECURITY", "METADATA"]
        assert config.ignore == ["CONFIG-003", "LIBRARY-001"]

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
                [tool.charmlint]
                ignore = ["STRUCTURE-002"]

                [tool.charmlint.per-rule-severity]
                "SECURITY-001" = "error"
            """)
        )
        config = load_config(tmp_path)
        assert config.severity_overrides["SECURITY-001"] == "error"
        assert "STRUCTURE-002" in config.ignore

    def test_pyproject_without_charmlint_section_ignored(self, tmp_path: pathlib.Path):
        (tmp_path / "pyproject.toml").write_text("[tool.ruff]\nline-length = 99\n")
        config = load_config(tmp_path)
        assert config == LintConfig()

    def test_standalone_charmlint_toml(self, tmp_path: pathlib.Path):
        (tmp_path / "charmlint.toml").write_text('select = ["SECURITY"]\n')
        config = load_config(tmp_path)
        assert config.select == ["SECURITY"]

    def test_dot_charmlint_toml(self, tmp_path: pathlib.Path):
        (tmp_path / ".charmlint.toml").write_text('select = ["METADATA"]\n')
        config = load_config(tmp_path)
        assert config.select == ["METADATA"]

    def test_standalone_preferred_over_pyproject(self, tmp_path: pathlib.Path):
        (tmp_path / "pyproject.toml").write_text('[tool.charmlint]\nselect = ["METADATA"]\n')
        (tmp_path / "charmlint.toml").write_text('select = ["SECURITY"]\n')
        config = load_config(tmp_path)
        assert config.select == ["SECURITY"]

    def test_walks_up_parent_directories(self, tmp_path: pathlib.Path):
        (tmp_path / "charmlint.toml").write_text('select = ["SECURITY"]\n')
        nested = tmp_path / "a" / "b"
        nested.mkdir(parents=True)
        config = load_config(nested)
        assert config.select == ["SECURITY"]

    def test_explicit_config_path_standalone(self, tmp_path: pathlib.Path):
        config_file = tmp_path / "custom.toml"
        config_file.write_text('select = ["SECURITY"]\n')
        config = load_config(tmp_path, config_path=config_file)
        assert config.select == ["SECURITY"]

    def test_explicit_config_path_pyproject(self, tmp_path: pathlib.Path):
        config_file = tmp_path / "pyproject.toml"
        config_file.write_text('[tool.charmlint]\nselect = ["SECURITY"]\n')
        config = load_config(tmp_path, config_path=config_file)
        assert config.select == ["SECURITY"]

    def test_malformed_standalone_raises(self, tmp_path: pathlib.Path):
        (tmp_path / "charmlint.toml").write_text("not = valid = toml\n")
        with pytest.raises(ConfigError):
            load_config(tmp_path)

    def test_malformed_ancestor_pyproject_warns_and_continues(
        self, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
    ):
        # Broken pyproject.toml higher in the tree, standalone charmlint
        # config in the charm dir — discovery should warn and use the
        # standalone.
        nested = tmp_path / "charm"
        nested.mkdir()
        (nested / "pyproject.toml").write_text("not = valid = toml\n")
        (tmp_path / "charmlint.toml").write_text('select = ["SECURITY"]\n')
        config = load_config(nested)
        assert config.select == ["SECURITY"]
        assert "Warning" in capsys.readouterr().err

    def test_pyproject_charmlint_not_a_table_raises(self, tmp_path: pathlib.Path):
        config_file = tmp_path / "pyproject.toml"
        config_file.write_text("[tool]\ncharmlint = 42\n")
        with pytest.raises(ConfigError, match="not a table"):
            load_config(tmp_path, config_path=config_file)

    def test_select_and_ignore_overlap_raises(self, tmp_path: pathlib.Path):
        config_file = tmp_path / "charmlint.toml"
        config_file.write_text('select = ["SECURITY"]\nignore = ["SECURITY"]\n')
        with pytest.raises(ConfigError, match="select and ignore both cover"):
            load_config(tmp_path)

    @pytest.mark.parametrize(
        ("toml", "reason"),
        [
            ('selct = ["SECURITY"]\n', "unknown key: selct"),
            (
                'per_rule_severity = {}\nsevrity = "info"\n',
                "unknown keys: per_rule_severity, sevrity",
            ),
            ('select = "SECURITY"\n', "select must be a list of strings"),
            ("extend-ignore = [1]\n", "extend-ignore must be a list of strings"),
            ('severity = "warn"\n', "severity must be one of error, warning, info, not 'warn'"),
            ("severity = 2\n", "severity must be one of"),
            ('per-rule-severity = "error"\n', "per-rule-severity must be a table"),
            (
                '[per-rule-severity]\n"SECURITY-001" = "critical"\n',
                "per-rule-severity for SECURITY-001 must be one of",
            ),
        ],
    )
    def test_misshapen_config_raises(self, tmp_path: pathlib.Path, toml: str, reason: str):
        # Each of these used to be dropped silently; a dropped ``select``
        # meant every rule ran.
        (tmp_path / "charmlint.toml").write_text(toml)
        with pytest.raises(ConfigError, match=re.escape(reason)):
            load_config(tmp_path)

    def test_misshapen_pyproject_table_raises(self, tmp_path: pathlib.Path):
        config_file = tmp_path / "pyproject.toml"
        config_file.write_text('[tool.charmlint]\nselect = "SECURITY"\n')
        with pytest.raises(ConfigError, match="select must be a list"):
            load_config(tmp_path, config_path=config_file)

    def test_severity_names_are_case_insensitive(self, tmp_path: pathlib.Path):
        (tmp_path / "charmlint.toml").write_text(
            'severity = "WARNING"\n[per-rule-severity]\n"SECURITY-001" = "Error"\n'
        )
        config = load_config(tmp_path)
        assert config.min_severity == Severity.WARNING
        assert config.severity_overrides == {"SECURITY-001": "error"}

    def test_malformed_explicit_config_raises(self, tmp_path: pathlib.Path):
        config_file = tmp_path / "custom.toml"
        config_file.write_text("not = valid = toml\n")
        with pytest.raises(ConfigError):
            load_config(tmp_path, config_path=config_file)
