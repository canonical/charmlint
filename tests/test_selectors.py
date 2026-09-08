"""Tests for naming rules by ID, name or category."""

import pathlib

import pytest

from charmlint import _selectors
from charmlint._cli import main
from charmlint._config import ConfigError, LintConfig, load_config
from charmlint._linter import lint
from charmlint._models import Severity
from charmlint._rules import CATEGORIES, Rule, get_all_rules
from tests.conftest import write_charmcraft_yaml


class TestResolve:
    """Tests for the token resolver."""

    def test_rule_id(self):
        assert _selectors.resolve("SECURITY-001") == {"SECURITY-001"}

    def test_rule_id_case_insensitive(self):
        assert _selectors.resolve("security-001") == {"SECURITY-001"}

    def test_rule_name(self):
        assert _selectors.resolve("secret-in-plain-config") == {"SECURITY-001"}

    def test_rule_name_case_insensitive(self):
        assert _selectors.resolve("Secret-In-Plain-Config") == {"SECURITY-001"}

    def test_category(self):
        resolved = _selectors.resolve("METADATA")
        assert resolved
        assert resolved == {r for r in get_all_rules() if r.startswith("METADATA-")}

    def test_unknown_token(self):
        assert _selectors.resolve("no-such-rule") == frozenset()

    def test_category_prefix_is_not_a_match(self):
        # ``METADATAA`` is not ``METADATA``: categories match exactly.
        assert _selectors.resolve("METADATAA") == frozenset()

    def test_empty_token(self):
        assert _selectors.resolve("   ") == frozenset()


class TestIsKnown:
    """A token is known if it could ever name a rule."""

    @pytest.mark.parametrize(
        "token",
        [
            "SECURITY-001",
            "secret-in-plain-config",
            "SECURITY",
            # A category with no rules yet, and a rule not yet written in
            # one: naming either is forward-looking, not a typo.
            "OBSERVABILITY",
            "OBSERVABILITY-005",
        ],
    )
    def test_known(self, token: str):
        assert _selectors.is_known(token)

    @pytest.mark.parametrize("token", ["SECRUITY", "SECRUITY-001", "no-such-rule", "", "-001"])
    def test_unknown(self, token: str):
        assert not _selectors.is_known(token)


class TestIsCategory:
    """Categories are the broad spelling; IDs and names the specific one."""

    def test_category(self):
        assert _selectors.is_category("SECURITY")

    def test_rule_id(self):
        assert not _selectors.is_category("SECURITY-001")

    def test_rule_name(self):
        assert not _selectors.is_category("secret-in-plain-config")


class TestNamesInConfig:
    """A rule name works wherever its ID does."""

    def test_ignore_by_name(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"display-name": "X"})
        report = lint(tmp_charm, LintConfig(ignore=["missing-name"]))
        assert "METADATA-001" not in {d.rule_id for d in report}

    def test_select_by_name(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"display-name": "X"})
        report = lint(tmp_charm, LintConfig(select=["missing-name"]))
        assert {d.rule_id for d in report} == {"METADATA-001"}

    def test_select_by_name_beats_ignored_category(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"display-name": "X"})
        config = LintConfig(select=["missing-name"], ignore=["METADATA"])
        assert "METADATA-001" in {d.rule_id for d in lint(tmp_charm, config)}

    def test_severity_override_by_name(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"display-name": "X"})
        config = LintConfig(severity_overrides={"missing-name": "warning"})
        meta001 = [d for d in lint(tmp_charm, config) if d.rule_id == "METADATA-001"]
        assert meta001
        assert meta001[0].severity == Severity.WARNING

    def test_severity_override_by_category(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"display-name": "X"})
        config = LintConfig(severity_overrides={"METADATA": "info"})
        meta = [d for d in lint(tmp_charm, config) if d.rule_id.startswith("METADATA-")]
        assert meta
        assert all(d.severity == Severity.INFO for d in meta)

    def test_specific_severity_override_beats_category(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"display-name": "X"})
        config = LintConfig(severity_overrides={"METADATA": "info", "METADATA-001": "warning"})
        meta001 = [d for d in lint(tmp_charm, config) if d.rule_id == "METADATA-001"]
        assert meta001[0].severity == Severity.WARNING


class TestUnknownTokensRejected:
    """A misspelled rule is an error, not a rule that never fires."""

    def test_unknown_select_rejected(self, tmp_path: pathlib.Path):
        (tmp_path / "charmlint.toml").write_text('select = ["SECRUITY"]\n')
        with pytest.raises(ConfigError, match="not a known rule ID, rule name or category"):
            load_config(tmp_path)

    def test_unknown_ignore_rejected(self, tmp_path: pathlib.Path):
        (tmp_path / "charmlint.toml").write_text('ignore = ["no-such-rule"]\n')
        with pytest.raises(ConfigError, match="no-such-rule"):
            load_config(tmp_path)

    def test_unknown_severity_override_key_rejected(self, tmp_path: pathlib.Path):
        (tmp_path / "charmlint.toml").write_text('[per-rule-severity]\n"no-such-rule" = "error"\n')
        with pytest.raises(ConfigError, match="no-such-rule"):
            load_config(tmp_path)

    def test_name_and_id_of_the_same_rule_conflict(self, tmp_path: pathlib.Path):
        (tmp_path / "charmlint.toml").write_text(
            'select = ["secret-in-plain-config"]\nignore = ["SECURITY-001"]\n'
        )
        with pytest.raises(ConfigError, match="select and ignore both cover: SECURITY-001"):
            load_config(tmp_path)

    def test_specific_select_and_broad_ignore_is_allowed(self, tmp_path: pathlib.Path):
        (tmp_path / "charmlint.toml").write_text(
            'select = ["secret-in-plain-config"]\nignore = ["SECURITY"]\n'
        )
        config = load_config(tmp_path)
        assert config.select == ["secret-in-plain-config"]

    def test_cli_rejects_unknown_select(
        self, tmp_charm: pathlib.Path, capsys: pytest.CaptureFixture[str]
    ):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        assert main([str(tmp_charm), "--select", "SECRUITY"]) == 2
        assert "not a known rule ID, rule name or category" in capsys.readouterr().err

    def test_cli_accepts_a_rule_name(
        self, tmp_charm: pathlib.Path, capsys: pytest.CaptureFixture[str]
    ):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        # The name selected a rule rather than being rejected: exit 0,
        # since METADATA-002 is a warning and --strict is not given.
        assert main([str(tmp_charm), "--select", "missing-display-name"]) == 0
        assert "METADATA-002" in capsys.readouterr().out


class TestRuleNameRegistry:
    """The registry keeps names usable as selectors."""

    def test_every_rule_has_a_unique_kebab_case_name(self):
        names = [rule.name for rule in get_all_rules().values()]
        assert len(names) == len(set(names))
        for name in names:
            assert name == name.lower()
            assert name.upper() not in CATEGORIES

    def test_every_rule_uses_a_catalogued_category(self):
        for rule in get_all_rules().values():
            assert rule.category in CATEGORIES

    def test_uncatalogued_category_rejected(self):
        with pytest.raises(ValueError, match="category"):

            class Bad(Rule):
                category = "NOSUCHCATEGORY"
                number = 1
                name = "bad-rule"
                description = "x"
                default_severity = Severity.INFO

                def check(self, context):
                    return []

    def test_non_kebab_case_name_rejected(self):
        with pytest.raises(ValueError, match="kebab-case"):

            class Bad(Rule):
                category = "SECURITY"
                number = 900
                name = "Not Kebab"
                description = "x"
                default_severity = Severity.INFO

                def check(self, context):
                    return []

    def test_name_that_spells_a_category_rejected(self):
        with pytest.raises(ValueError, match="must not be a category name"):

            class Bad(Rule):
                category = "SECURITY"
                number = 901
                name = "security"
                description = "x"
                default_severity = Severity.INFO

                def check(self, context):
                    return []

    def test_duplicate_name_rejected(self):
        with pytest.raises(ValueError, match="Duplicate rule name"):

            class Bad(Rule):
                category = "SECURITY"
                number = 902
                name = "secret-in-plain-config"
                description = "x"
                default_severity = Severity.INFO

                def check(self, context):
                    return []
