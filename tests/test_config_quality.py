"""Tests for config quality rules."""

import pathlib
from typing import Any

import pytest

from charmlint._linter import lint
from charmlint._models import Severity
from tests.conftest import write_charmcraft_yaml


def _write_options(charm_dir: pathlib.Path, options: dict[str, Any]) -> None:
    write_charmcraft_yaml(charm_dir, {"name": "test", "config": {"options": options}})


def _diags(charm_dir: pathlib.Path, rule_id: str):
    return [d for d in lint(charm_dir) if d.rule_id == rule_id]


class TestConfigMissingType:
    """Tests for CONFIG-001 — config options without a type."""

    def test_missing_type_flagged(self, tmp_charm: pathlib.Path):
        _write_options(tmp_charm, {"foo": {"description": "An option", "default": ""}})
        diags = _diags(tmp_charm, "CONFIG-001")
        assert len(diags) == 1
        assert diags[0].severity == Severity.WARNING
        assert "foo" in diags[0].message
        assert diags[0].path == "charmcraft.yaml"

    @pytest.mark.parametrize("option_type", ["string", "int", "float", "boolean", "secret"])
    def test_type_present_not_flagged(self, tmp_charm: pathlib.Path, option_type: str):
        _write_options(
            tmp_charm, {"foo": {"type": option_type, "description": "x", "default": None}}
        )
        assert not _diags(tmp_charm, "CONFIG-001")

    def test_empty_type_flagged(self, tmp_charm: pathlib.Path):
        _write_options(tmp_charm, {"foo": {"type": "", "description": "x", "default": ""}})
        assert len(_diags(tmp_charm, "CONFIG-001")) == 1

    def test_non_mapping_option_flagged(self, tmp_charm: pathlib.Path):
        # Some charms write `options: {foo: string}`; that is not a valid
        # option spec, so every per-key check applies.
        _write_options(tmp_charm, {"foo": "string"})
        assert len(_diags(tmp_charm, "CONFIG-001")) == 1

    def test_one_diagnostic_per_option(self, tmp_charm: pathlib.Path):
        _write_options(
            tmp_charm,
            {
                "foo": {"description": "x", "default": ""},
                "bar": {"description": "y", "default": ""},
                "baz": {"type": "int", "description": "z", "default": 1},
            },
        )
        diags = _diags(tmp_charm, "CONFIG-001")
        assert {"foo", "bar"} == {d.message.split("'")[1] for d in diags}

    def test_no_config_section(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        assert not _diags(tmp_charm, "CONFIG-001")

    def test_line_number_reported(self, tmp_charm: pathlib.Path):
        (tmp_charm / "charmcraft.yaml").write_text(
            "name: test\nconfig:\n  options:\n    foo:\n      description: An option\n"
        )
        diags = _diags(tmp_charm, "CONFIG-001")
        assert len(diags) == 1
        assert diags[0].line == 4

    def test_config_yaml_source(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        (tmp_charm / "config.yaml").write_text("options:\n  foo:\n    description: An option\n")
        diags = _diags(tmp_charm, "CONFIG-001")
        assert len(diags) == 1
        assert diags[0].path == "config.yaml"


class TestConfigMissingDefault:
    """Tests for CONFIG-002 — config options without a default value."""

    def test_missing_default_flagged(self, tmp_charm: pathlib.Path):
        _write_options(tmp_charm, {"foo": {"type": "string", "description": "x"}})
        diags = _diags(tmp_charm, "CONFIG-002")
        assert len(diags) == 1
        assert diags[0].severity == Severity.INFO
        assert "foo" in diags[0].message

    def test_default_present_not_flagged(self, tmp_charm: pathlib.Path):
        _write_options(tmp_charm, {"foo": {"type": "string", "description": "x", "default": "v"}})
        assert not _diags(tmp_charm, "CONFIG-002")

    @pytest.mark.parametrize("default", ["", 0, False, None])
    def test_falsy_default_not_flagged(self, tmp_charm: pathlib.Path, default: Any):
        # An explicit falsy default is still a default; only its absence
        # is a finding.
        _write_options(
            tmp_charm, {"foo": {"type": "string", "description": "x", "default": default}}
        )
        assert not _diags(tmp_charm, "CONFIG-002")

    def test_secret_option_not_flagged(self, tmp_charm: pathlib.Path):
        # A secret option takes a user-supplied secret URI; there is no
        # default the charm author could sensibly ship.
        _write_options(tmp_charm, {"api-key": {"type": "secret", "description": "x"}})
        assert not _diags(tmp_charm, "CONFIG-002")

    def test_non_mapping_option_not_flagged(self, tmp_charm: pathlib.Path):
        # A malformed spec is CONFIG-001's finding to report; repeating
        # it here would just add noise.
        _write_options(tmp_charm, {"foo": "string"})
        assert not _diags(tmp_charm, "CONFIG-002")


class TestConfigMissingDescription:
    """Tests for CONFIG-003 — config options without a description."""

    def test_missing_description_flagged(self, tmp_charm: pathlib.Path):
        _write_options(tmp_charm, {"foo": {"type": "string", "default": ""}})
        diags = _diags(tmp_charm, "CONFIG-003")
        assert len(diags) == 1
        assert diags[0].severity == Severity.WARNING
        assert "foo" in diags[0].message

    def test_description_present_not_flagged(self, tmp_charm: pathlib.Path):
        _write_options(tmp_charm, {"foo": {"type": "string", "default": "", "description": "x"}})
        assert not _diags(tmp_charm, "CONFIG-003")

    @pytest.mark.parametrize("description", ["", "   ", "\n"])
    def test_blank_description_flagged(self, tmp_charm: pathlib.Path, description: str):
        _write_options(
            tmp_charm, {"foo": {"type": "string", "default": "", "description": description}}
        )
        assert len(_diags(tmp_charm, "CONFIG-003")) == 1

    def test_non_mapping_option_flagged(self, tmp_charm: pathlib.Path):
        _write_options(tmp_charm, {"foo": "string"})
        assert len(_diags(tmp_charm, "CONFIG-003")) == 1


class TestConfigRulesTogether:
    """A fully specified option should trip none of the config rules."""

    def test_complete_option_clean(self, tmp_charm: pathlib.Path):
        _write_options(
            tmp_charm,
            {"port": {"type": "int", "default": 8080, "description": "The HTTP port"}},
        )
        ids = {d.rule_id for d in lint(tmp_charm)}
        assert not ids & {"CONFIG-001", "CONFIG-002", "CONFIG-003"}

    def test_empty_options_section_clean(self, tmp_charm: pathlib.Path):
        # `config: {options: }` declares an empty option set. The literal
        # key 'options' must not be mistaken for an option name.
        (tmp_charm / "charmcraft.yaml").write_text("name: test\nconfig:\n  options:\n")
        ids = {d.rule_id for d in lint(tmp_charm)}
        assert not ids & {"CONFIG-001", "CONFIG-002", "CONFIG-003"}

    def test_bare_option_trips_all_three(self, tmp_charm: pathlib.Path):
        _write_options(tmp_charm, {"foo": {}})
        ids = {d.rule_id for d in lint(tmp_charm)}
        assert {"CONFIG-001", "CONFIG-002", "CONFIG-003"} <= ids


class TestConfigNoqa:
    """The config rules are the first to report per-option line numbers.

    That makes them the only rules an inline ``# noqa`` can target, so
    the line anchoring is exercised here rather than in ``test_noqa.py``.
    """

    # A bare option (`foo:` with no spec) trips CONFIG-001 and CONFIG-003
    # but not CONFIG-002, which skips malformed specs.
    _BARE_OPTION_RULES = {"CONFIG-001", "CONFIG-003"}

    def _lint_options_block(self, charm_dir: pathlib.Path, block: str) -> set[str]:
        charmcraft = f"name: test\nconfig:\n  options:\n{block}"
        (charm_dir / "charmcraft.yaml").write_text(charmcraft)
        return {d.rule_id for d in lint(charm_dir) if d.rule_id.startswith("CONFIG-")}

    def test_bare_inline_noqa_suppresses_all(self, tmp_charm: pathlib.Path):
        assert not self._lint_options_block(tmp_charm, "    foo:  # noqa\n")

    def test_inline_noqa_by_rule_id(self, tmp_charm: pathlib.Path):
        ids = self._lint_options_block(tmp_charm, "    foo:  # noqa: CONFIG-001\n")
        assert ids == {"CONFIG-003"}

    def test_inline_noqa_by_category(self, tmp_charm: pathlib.Path):
        assert not self._lint_options_block(tmp_charm, "    foo:  # noqa: CONFIG\n")

    def test_inline_noqa_for_another_rule_does_not_suppress(self, tmp_charm: pathlib.Path):
        ids = self._lint_options_block(tmp_charm, "    foo:  # noqa: SECURITY-001\n")
        assert ids == self._BARE_OPTION_RULES

    def test_noqa_suppresses_only_its_own_option(self, tmp_charm: pathlib.Path):
        ids = self._lint_options_block(tmp_charm, "    foo:  # noqa\n    bar:\n")
        assert ids == self._BARE_OPTION_RULES
        diags = _diags(tmp_charm, "CONFIG-001")
        assert [d.message.split("'")[1] for d in diags] == ["bar"]

    def test_noqa_on_nested_key_does_not_suppress(self, tmp_charm: pathlib.Path):
        # Diagnostics anchor to the option's own key line, so a comment
        # on a child key is not a suppression for the option.
        ids = self._lint_options_block(tmp_charm, "    foo:\n      type: string  # noqa\n")
        assert ids == {"CONFIG-002", "CONFIG-003"}

    def test_file_level_noqa(self, tmp_charm: pathlib.Path):
        (tmp_charm / "charmcraft.yaml").write_text(
            "# charmlint: noqa: CONFIG-002\nname: test\nconfig:\n  options:\n"
            "    foo:\n      type: string\n      description: An option\n"
        )
        assert not {d.rule_id for d in lint(tmp_charm) if d.rule_id.startswith("CONFIG-")}

    def test_noqa_in_config_yaml(self, tmp_charm: pathlib.Path):
        # Options read from config.yaml must resolve their noqa against
        # that file, not charmcraft.yaml.
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        (tmp_charm / "config.yaml").write_text(
            "options:\n  foo:  # noqa: CONFIG-003\n    type: string\n    default: ''\n  bar:\n"
        )
        ids = {d.rule_id for d in lint(tmp_charm) if d.rule_id.startswith("CONFIG-")}
        assert ids == self._BARE_OPTION_RULES
        assert [d.message.split("'")[1] for d in _diags(tmp_charm, "CONFIG-003")] == ["bar"]
