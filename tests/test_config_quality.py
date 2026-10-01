"""Tests for config quality rules."""

import pathlib
from typing import Any

import pytest

from charmlint._linter import lint
from charmlint._models import Severity
from tests.conftest import write_charm_source, write_charmcraft_yaml


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
    """Tests for ``# noqa`` suppression of the config rules.

    Config diagnostics carry the option's own key line, so an inline
    directive on that line targets that option alone. ``test_noqa.py``
    covers directive parsing; this covers the line anchoring.
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

    def test_file_level_ignore(self, tmp_charm: pathlib.Path):
        (tmp_charm / "charmcraft.yaml").write_text(
            "# charmlint: file-ignore[CONFIG-002]\nname: test\nconfig:\n  options:\n"
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


class TestConfigOptionUndeclared:
    """Tests for CONFIG-006 — config keys read in src/ but never declared."""

    _DECLARED = {"port": {"type": "int", "default": 8080, "description": "HTTP port"}}

    def _lint_charm(self, charm_dir: pathlib.Path, source: str, **kwargs: Any):
        _write_options(charm_dir, kwargs.pop("options", self._DECLARED))
        write_charm_source(charm_dir, source, **kwargs)
        return _diags(charm_dir, "CONFIG-006")

    _CHARM = """\
import ops


class MyCharm(ops.CharmBase):
    def _on_start(self, event):
        {body}
"""

    def _lint_body(self, charm_dir: pathlib.Path, body: str, **kwargs: Any):
        return self._lint_charm(charm_dir, self._CHARM.format(body=body), **kwargs)

    def test_undeclared_subscript_flagged(self, tmp_charm: pathlib.Path):
        diags = self._lint_body(tmp_charm, 'print(self.config["prot"])')
        assert len(diags) == 1
        assert diags[0].severity == Severity.ERROR
        assert "prot" in diags[0].message
        assert diags[0].path == "src/charm.py"
        assert diags[0].line == 6

    def test_undeclared_get_flagged(self, tmp_charm: pathlib.Path):
        diags = self._lint_body(tmp_charm, 'print(self.config.get("prot", 1))')
        assert len(diags) == 1
        assert "prot" in diags[0].message

    def test_declared_key_not_flagged(self, tmp_charm: pathlib.Path):
        assert not self._lint_body(
            tmp_charm, 'print(self.config["port"], self.config.get("port"))'
        )

    @pytest.mark.parametrize(
        "spelling",
        [
            "self.model.config",
            "self.charm.config",
            "self.charm.model.config",
            "charm.config",
            "charm.model.config",
        ],
    )
    def test_model_config_spellings_flagged(self, tmp_charm: pathlib.Path, spelling: str):
        source = f'def f(charm, self):\n    print({spelling}["prot"])\n'
        diags = self._lint_charm(tmp_charm, source)
        assert len(diags) == 1

    def test_self_config_outside_charm_class_ignored(self, tmp_charm: pathlib.Path):
        # A helper class with its own ``self.config`` dict is common, and its
        # keys have nothing to do with the charm's config schema.
        source = 'class Workload:\n    def run(self):\n        print(self.config["prot"])\n'
        assert not self._lint_charm(tmp_charm, source)

    def test_charm_named_base_class_checked(self, tmp_charm: pathlib.Path):
        # Charms routinely subclass an intermediate base of their own.
        source = (
            "from base import OpenStackCharm\n\n\n"
            "class MyCharm(OpenStackCharm):\n"
            '    def run(self):\n        print(self.config["prot"])\n'
        )
        assert len(self._lint_charm(tmp_charm, source)) == 1

    def test_computed_key_ignored(self, tmp_charm: pathlib.Path):
        assert not self._lint_body(tmp_charm, "print(self.config[name], self.config.get(name))")

    def test_get_without_arguments_ignored(self, tmp_charm: pathlib.Path):
        assert not self._lint_body(tmp_charm, "print(self.config.get())")

    def test_other_get_calls_ignored(self, tmp_charm: pathlib.Path):
        assert not self._lint_body(tmp_charm, 'print(self.stored.get("prot"), d["prot"])')

    def test_no_options_declared_skipped(self, tmp_charm: pathlib.Path):
        # A charm keeping its metadata somewhere the linter did not look
        # would otherwise light up entirely.
        assert not self._lint_body(tmp_charm, 'print(self.config["prot"])', options={})

    def test_library_code_ignored(self, tmp_charm: pathlib.Path):
        # A library reads the config of whichever charm uses it.
        lib = tmp_charm / "lib" / "charms" / "test" / "v0"
        lib.mkdir(parents=True)
        (lib / "thing.py").write_text('def f(charm):\n    print(charm.config["prot"])\n')
        assert not self._lint_charm(tmp_charm, "")

    def test_one_diagnostic_per_read(self, tmp_charm: pathlib.Path):
        diags = self._lint_body(
            tmp_charm, 'print(self.config["prot"])\n        print(self.config["prot"])'
        )
        assert [d.line for d in diags] == [6, 7]


class TestConfigDefaultTypeMismatch:
    """Tests for CONFIG-007 — a default that contradicts the declared type."""

    @pytest.mark.parametrize(
        ("option_type", "default", "expected"),
        [
            ("int", "8080", "a string"),
            ("int", 80.5, "a float"),
            ("int", True, "a boolean"),
            ("float", "0.5", "a string"),
            ("float", False, "a boolean"),
            ("boolean", "yes", "a string"),
            ("boolean", 1, "an integer"),
            ("string", 8080, "an integer"),
            ("string", True, "a boolean"),
            ("secret", 1, "an integer"),
        ],
    )
    def test_mismatch_flagged(
        self, tmp_charm: pathlib.Path, option_type: str, default: Any, expected: str
    ):
        _write_options(
            tmp_charm, {"foo": {"type": option_type, "default": default, "description": "x"}}
        )
        diags = _diags(tmp_charm, "CONFIG-007")
        assert len(diags) == 1
        assert diags[0].severity == Severity.ERROR
        assert f"'{option_type}'" in diags[0].message
        assert expected in diags[0].message

    @pytest.mark.parametrize(
        ("option_type", "default"),
        [
            ("int", 8080),
            ("float", 0.5),
            # YAML has no way to write an integral float, so an int is
            # the only way to spell a float option's default of 1.
            ("float", 1),
            ("boolean", True),
            ("boolean", False),
            ("string", "debug"),
            ("string", ""),
            ("secret", "secret:cvh7kruupa1s46bqvuig"),
        ],
    )
    def test_matching_default_clean(self, tmp_charm: pathlib.Path, option_type: str, default: Any):
        _write_options(
            tmp_charm, {"foo": {"type": option_type, "default": default, "description": "x"}}
        )
        assert not _diags(tmp_charm, "CONFIG-007")

    def test_yaml_boolean_default_for_string_option_flagged(self, tmp_charm: pathlib.Path):
        # Under YAML 1.1 an unquoted `no` is the boolean False, which is
        # the whole reason this rule earns its keep.
        (tmp_charm / "charmcraft.yaml").write_text(
            "name: test\nconfig:\n  options:\n    tls:\n      type: string\n      default: no\n"
        )
        diags = _diags(tmp_charm, "CONFIG-007")
        assert len(diags) == 1
        assert "a boolean" in diags[0].message

    def test_no_default_clean(self, tmp_charm: pathlib.Path):
        _write_options(tmp_charm, {"foo": {"type": "int", "description": "x"}})
        assert not _diags(tmp_charm, "CONFIG-007")

    def test_explicit_null_default_clean(self, tmp_charm: pathlib.Path):
        # `default: null` declares no value, so there is nothing to
        # check it against.
        _write_options(tmp_charm, {"foo": {"type": "int", "default": None, "description": "x"}})
        assert not _diags(tmp_charm, "CONFIG-007")

    def test_missing_type_clean(self, tmp_charm: pathlib.Path):
        # CONFIG-001's finding; repeating it here would say nothing new.
        _write_options(tmp_charm, {"foo": {"default": "8080", "description": "x"}})
        assert not _diags(tmp_charm, "CONFIG-007")

    def test_unknown_type_clean(self, tmp_charm: pathlib.Path):
        _write_options(tmp_charm, {"foo": {"type": "integer", "default": "8", "description": "x"}})
        assert not _diags(tmp_charm, "CONFIG-007")

    def test_non_mapping_option_clean(self, tmp_charm: pathlib.Path):
        _write_options(tmp_charm, {"foo": "string"})
        assert not _diags(tmp_charm, "CONFIG-007")

    def test_diagnostic_anchors_to_the_default(self, tmp_charm: pathlib.Path):
        (tmp_charm / "charmcraft.yaml").write_text(
            "name: test\nconfig:\n  options:\n    port:\n      type: int\n      default: '8080'\n"
        )
        diags = _diags(tmp_charm, "CONFIG-007")
        assert [(d.path, d.line) for d in diags] == [("charmcraft.yaml", 6)]

    def test_one_diagnostic_per_option(self, tmp_charm: pathlib.Path):
        _write_options(
            tmp_charm,
            {
                "a": {"type": "int", "default": "1", "description": "x"},
                "b": {"type": "int", "default": 2, "description": "y"},
                "c": {"type": "boolean", "default": "true", "description": "z"},
            },
        )
        diags = _diags(tmp_charm, "CONFIG-007")
        assert {d.message.split("'")[1] for d in diags} == {"a", "c"}
