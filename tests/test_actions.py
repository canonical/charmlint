"""Tests for ACTIONS-### rules."""

import pathlib

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
            "import ops\n\nclass C(ops.CharmBase):\n    pass\n",
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
            "import ops\n\n"
            "class C(ops.CharmBase):\n"
            "    def __init__(self, *args):\n"
            "        super().__init__(*args)\n"
            "        self.framework.observe(self.on.do_thing_action, self._on_do_thing)\n"
            "    def _on_do_thing(self, event):\n"
            "        pass\n",
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
            "import ops\n\n"
            "class C(ops.CharmBase):\n"
            "    def __init__(self, framework):\n"
            "        super().__init__(framework)\n"
            "        framework.observe(self.on.do_thing_action, self._on_do_thing)\n"
            "    def _on_do_thing(self, event):\n"
            "        pass\n",
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
            "import ops\n\n"
            "class C(ops.CharmBase):\n"
            "    def __init__(self, *args):\n"
            "        super().__init__(*args)\n"
            "        self.framework.observe(self.on['do-thing'].action, self._on_do_thing)\n"
            "    def _on_do_thing(self, event):\n"
            "        pass\n",
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
            "import ops\n\n"
            "class C(ops.CharmBase):\n"
            "    def __init__(self, *args):\n"
            "        super().__init__(*args)\n"
            "        self.framework.observe(\n"
            "            getattr(self.on, 'do_thing_action'), self._on_do_thing\n"
            "        )\n"
            "    def _on_do_thing(self, event):\n"
            "        pass\n",
        )
        report = lint(tmp_charm)
        assert "ACTIONS-001" not in {d.rule_id for d in report}

    def test_legacy_actions_yaml_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        (tmp_charm / "actions.yaml").write_text("do-thing:\n  description: x\n")
        write_charm_source(
            tmp_charm,
            "import ops\n\nclass C(ops.CharmBase):\n    pass\n",
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
            "class X:\n"
            "    def __init__(self, charm):\n"
            "        charm.framework.observe(charm.on.do_thing_action, self._h)\n"
            "    def _h(self, event):\n"
            "        pass\n",
        )
        write_charm_source(
            tmp_charm,
            "import ops\n\nclass C(ops.CharmBase):\n    pass\n",
        )
        report = lint(tmp_charm)
        assert "ACTIONS-001" in {d.rule_id for d in report}
