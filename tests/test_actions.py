"""Tests for ACTIONS-### rules."""

import pathlib
import textwrap

from charmlint._linter import lint
from charmlint._models import Severity
from tests.conftest import write_charm_source, write_charmcraft_yaml


class TestActionMissingObserver:
    """ACTIONS-001 — declared actions must have observers."""

    def test_action_missing_observer_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "test", "actions": {"do-thing": {"description": "x"}}},
        )
        write_charm_source(
            tmp_charm,
            textwrap.dedent("""\
                import ops

                class C(ops.CharmBase):
                    pass
            """),
        )
        report = lint(tmp_charm)
        actions = [d for d in report if d.rule_id == "ACTIONS-001"]
        assert len(actions) == 1
        assert actions[0].severity == Severity.WARNING
        assert "do-thing" in actions[0].message

    def test_action_with_observer_not_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "test", "actions": {"do-thing": {"description": "x"}}},
        )
        write_charm_source(
            tmp_charm,
            textwrap.dedent("""\
                import ops

                class C(ops.CharmBase):
                    def __init__(self, *args):
                        super().__init__(*args)
                        self.framework.observe(self.on.do_thing_action, self._on_do_thing)
                    def _on_do_thing(self, event):
                        pass
            """),
        )
        report = lint(tmp_charm)
        assert "ACTIONS-001" not in {d.rule_id for d in report}

    def test_bare_framework_observe_recognised(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "test", "actions": {"do-thing": {"description": "x"}}},
        )
        write_charm_source(
            tmp_charm,
            textwrap.dedent("""\
                import ops

                class C(ops.CharmBase):
                    def __init__(self, framework):
                        super().__init__(framework)
                        framework.observe(self.on.do_thing_action, self._on_do_thing)
                    def _on_do_thing(self, event):
                        pass
            """),
        )
        report = lint(tmp_charm)
        assert "ACTIONS-001" not in {d.rule_id for d in report}

    def test_subscript_observer_form_recognised(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "test", "actions": {"do-thing": {"description": "x"}}},
        )
        write_charm_source(
            tmp_charm,
            textwrap.dedent("""\
                import ops

                class C(ops.CharmBase):
                    def __init__(self, *args):
                        super().__init__(*args)
                        self.framework.observe(self.on['do-thing'].action, self._on_do_thing)
                    def _on_do_thing(self, event):
                        pass
            """),
        )
        report = lint(tmp_charm)
        assert "ACTIONS-001" not in {d.rule_id for d in report}

    def test_getattr_observer_form_recognised(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "test", "actions": {"do-thing": {"description": "x"}}},
        )
        write_charm_source(
            tmp_charm,
            textwrap.dedent("""\
                import ops

                class C(ops.CharmBase):
                    def __init__(self, *args):
                        super().__init__(*args)
                        self.framework.observe(
                            getattr(self.on, 'do_thing_action'), self._on_do_thing
                        )
                    def _on_do_thing(self, event):
                        pass
            """),
        )
        report = lint(tmp_charm)
        assert "ACTIONS-001" not in {d.rule_id for d in report}

    def test_legacy_actions_yaml_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        (tmp_charm / "actions.yaml").write_text("do-thing:\n  description: x\n")
        write_charm_source(
            tmp_charm,
            textwrap.dedent("""\
                import ops

                class C(ops.CharmBase):
                    pass
            """),
        )
        report = lint(tmp_charm)
        actions = [d for d in report if d.rule_id == "ACTIONS-001"]
        assert len(actions) == 1
        assert "do-thing" in actions[0].message

    def test_no_actions_declared_no_diagnostic(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        report = lint(tmp_charm)
        assert "ACTIONS-001" not in {d.rule_id for d in report}

    def test_observer_inside_lib_is_ignored(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "test", "actions": {"do-thing": {"description": "x"}}},
        )
        # Observer wired up inside lib/ shouldn't count — charm code lives in src/.
        (tmp_charm / "lib").mkdir()
        (tmp_charm / "lib" / "helper.py").write_text(
            textwrap.dedent("""\
                class X:
                    def __init__(self, charm):
                        charm.framework.observe(charm.on.do_thing_action, self._h)
                    def _h(self, event):
                        pass
            """),
        )
        write_charm_source(
            tmp_charm,
            textwrap.dedent("""\
                import ops

                class C(ops.CharmBase):
                    pass
            """),
        )
        report = lint(tmp_charm)
        assert "ACTIONS-001" in {d.rule_id for d in report}


class TestActionMissingAdditionalProperties:
    """ACTIONS-002 — declared actions must state `additionalProperties`."""

    def test_missing_additional_properties_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "test", "actions": {"do-thing": {"description": "x"}}},
        )
        report = lint(tmp_charm)
        found = [d for d in report if d.rule_id == "ACTIONS-002"]
        assert len(found) == 1
        assert found[0].severity == Severity.WARNING
        assert "do-thing" in found[0].message

    def test_additional_properties_false_not_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "actions": {"do-thing": {"description": "x", "additionalProperties": False}},
            },
        )
        report = lint(tmp_charm)
        assert "ACTIONS-002" not in {d.rule_id for d in report}

    def test_additional_properties_true_not_flagged(self, tmp_charm: pathlib.Path):
        # Either value is accepted — the rule only asks that the charm chose.
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "actions": {"do-thing": {"description": "x", "additionalProperties": True}},
            },
        )
        report = lint(tmp_charm)
        assert "ACTIONS-002" not in {d.rule_id for d in report}

    def test_action_without_body_flagged(self, tmp_charm: pathlib.Path):
        (tmp_charm / "charmcraft.yaml").write_text("name: test\nactions:\n  do-thing:\n")
        report = lint(tmp_charm)
        found = [d for d in report if d.rule_id == "ACTIONS-002"]
        assert len(found) == 1
        assert "do-thing" in found[0].message

    def test_each_action_flagged_separately(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "actions": {
                    "do-thing": {"description": "x"},
                    "do-other": {"description": "y", "additionalProperties": False},
                    "do-third": {"description": "z"},
                },
            },
        )
        report = lint(tmp_charm)
        found = [d for d in report if d.rule_id == "ACTIONS-002"]
        assert len(found) == 2
        flagged = {d.message.split("'")[1] for d in found}
        assert flagged == {"do-thing", "do-third"}

    def test_legacy_actions_yaml_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        (tmp_charm / "actions.yaml").write_text("do-thing:\n  description: x\n")
        report = lint(tmp_charm)
        found = [d for d in report if d.rule_id == "ACTIONS-002"]
        assert len(found) == 1
        assert "do-thing" in found[0].message

    def test_no_actions_declared_no_diagnostic(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        report = lint(tmp_charm)
        assert "ACTIONS-002" not in {d.rule_id for d in report}


class TestActionMissingDescription:
    """ACTIONS-003 — declared actions must have a description."""

    def test_action_without_description_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test", "actions": {"do-thing": {}}})
        report = lint(tmp_charm)
        found = [d for d in report if d.rule_id == "ACTIONS-003"]
        assert len(found) == 1
        assert found[0].severity == Severity.WARNING
        assert "do-thing" in found[0].message

    def test_action_with_description_not_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "test", "actions": {"do-thing": {"description": "Does a thing"}}},
        )
        report = lint(tmp_charm)
        assert "ACTIONS-003" not in {d.rule_id for d in report}

    def test_empty_description_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "test", "actions": {"do-thing": {"description": "   "}}},
        )
        report = lint(tmp_charm)
        assert "ACTIONS-003" in {d.rule_id for d in report}

    def test_action_with_no_body_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test", "actions": {"do-thing": None}})
        report = lint(tmp_charm)
        assert "ACTIONS-003" in {d.rule_id for d in report}

    def test_no_actions_declared_no_diagnostic(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        report = lint(tmp_charm)
        assert "ACTIONS-003" not in {d.rule_id for d in report}

    def test_anchored_to_the_action_line(self, tmp_charm: pathlib.Path):
        (tmp_charm / "charmcraft.yaml").write_text(
            "name: test\n"
            "actions:\n"
            "  documented:\n"
            "    description: d\n"
            "  do-thing:\n"
            "    params: {}\n"
        )
        report = lint(tmp_charm)
        found = [d for d in report if d.rule_id == "ACTIONS-003"]
        assert len(found) == 1
        assert found[0].path == "charmcraft.yaml"
        assert found[0].line == 5

    def test_anchored_to_legacy_actions_yaml(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        (tmp_charm / "actions.yaml").write_text("do-thing:\n  params: {}\n")
        report = lint(tmp_charm)
        found = [d for d in report if d.rule_id == "ACTIONS-003"]
        assert len(found) == 1
        assert found[0].path == "actions.yaml"
        assert found[0].line == 1

    def test_noqa_on_the_action_line_suppresses(self, tmp_charm: pathlib.Path):
        (tmp_charm / "charmcraft.yaml").write_text(
            "name: test\nactions:\n  do-thing:  # noqa: ACTIONS-003\n    params: {}\n"
        )
        report = lint(tmp_charm)
        assert "ACTIONS-003" not in {d.rule_id for d in report}

    def test_noqa_on_a_different_line_does_not_suppress(self, tmp_charm: pathlib.Path):
        (tmp_charm / "charmcraft.yaml").write_text(
            "name: test  # noqa: ACTIONS-003\nactions:\n  do-thing:\n    params: {}\n"
        )
        report = lint(tmp_charm)
        assert "ACTIONS-003" in {d.rule_id for d in report}


class TestActionParamMissingDescription:
    """ACTIONS-004 — action parameters must have a description."""

    def test_param_without_description_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "actions": {
                    "do-thing": {
                        "description": "Does a thing",
                        "params": {"verbose": {"type": "boolean"}},
                    },
                },
            },
        )
        report = lint(tmp_charm)
        found = [d for d in report if d.rule_id == "ACTIONS-004"]
        assert len(found) == 1
        assert found[0].severity == Severity.INFO
        assert "verbose" in found[0].message

    def test_param_with_description_not_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "actions": {
                    "do-thing": {
                        "description": "Does a thing",
                        "params": {
                            "verbose": {"type": "boolean", "description": "Log more"},
                        },
                    },
                },
            },
        )
        report = lint(tmp_charm)
        assert "ACTIONS-004" not in {d.rule_id for d in report}

    def test_nested_properties_form_handled(self, tmp_charm: pathlib.Path):
        # Some charms nest an explicit JSON Schema `properties` inside `params`.
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "actions": {
                    "do-thing": {
                        "description": "Does a thing",
                        "params": {
                            "properties": {"verbose": {"type": "boolean"}},
                            "required": ["verbose"],
                        },
                    },
                },
            },
        )
        report = lint(tmp_charm)
        found = [d for d in report if d.rule_id == "ACTIONS-004"]
        assert len(found) == 1
        assert "verbose" in found[0].message

    def test_action_without_params_no_diagnostic(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "test", "actions": {"do-thing": {"description": "Does a thing"}}},
        )
        report = lint(tmp_charm)
        assert "ACTIONS-004" not in {d.rule_id for d in report}

    def test_non_mapping_param_ignored(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "actions": {
                    "do-thing": {"description": "Does a thing", "params": {"verbose": "boolean"}},
                },
            },
        )
        report = lint(tmp_charm)
        assert "ACTIONS-004" not in {d.rule_id for d in report}

    def test_anchored_to_the_param_line(self, tmp_charm: pathlib.Path):
        (tmp_charm / "charmcraft.yaml").write_text(
            "name: test\n"
            "actions:\n"
            "  do-thing:\n"
            "    description: d\n"
            "    params:\n"
            "      verbose:\n"
            "        type: boolean\n"
        )
        report = lint(tmp_charm)
        found = [d for d in report if d.rule_id == "ACTIONS-004"]
        assert len(found) == 1
        assert found[0].path == "charmcraft.yaml"
        assert found[0].line == 6

    def test_noqa_on_the_param_line_suppresses(self, tmp_charm: pathlib.Path):
        (tmp_charm / "charmcraft.yaml").write_text(
            "name: test\n"
            "actions:\n"
            "  do-thing:\n"
            "    description: d\n"
            "    params:\n"
            "      verbose:  # noqa: ACTIONS-004\n"
            "        type: boolean\n"
        )
        report = lint(tmp_charm)
        assert "ACTIONS-004" not in {d.rule_id for d in report}
