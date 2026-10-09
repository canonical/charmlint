"""Tests for TESTING-### rules."""

import pathlib
import textwrap

import pytest

from charmlint._linter import lint
from charmlint._models import Severity
from tests.conftest import write_charmcraft_yaml

_RULE = "TESTING-003"


def _write(charm_dir: pathlib.Path, relative: str, source: str) -> pathlib.Path:
    """Write *source* to *relative* inside the charm, creating parents."""
    path = charm_dir / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(source))
    return path


def _lint_unit_test(charm_dir: pathlib.Path, source: str):
    """Lint a charm whose tests/unit/test_charm.py is *source*."""
    write_charmcraft_yaml(charm_dir, {"name": "test-charm"})
    _write(charm_dir, "tests/unit/test_charm.py", source)
    report = lint(charm_dir)
    return [d for d in report if d.rule_id == _RULE]


_HARNESS_TEST = """\
    import ops.testing

    def test_charm():
        harness = ops.testing.Harness(MyCharm)
        harness.begin()
"""


class TestUsesHarness:
    """TESTING-003 — unit tests must not use the deprecated Harness."""

    def test_attribute_spelling_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_unit_test(tmp_charm, _HARNESS_TEST)
        assert len(findings) == 1
        assert findings[0].severity == Severity.WARNING
        assert findings[0].path == "tests/unit/test_charm.py"
        assert findings[0].line == 4
        assert "Harness" in findings[0].message

    def test_from_import_spelling_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_unit_test(
            tmp_charm,
            """\
            from ops.testing import Harness

            def test_charm():
                harness = Harness(MyCharm)
            """,
        )
        assert len(findings) == 1
        assert findings[0].line == 4

    def test_aliased_import_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_unit_test(
            tmp_charm,
            """\
            from ops.testing import Harness as H

            def test_charm():
                harness = H(MyCharm)
            """,
        )
        assert len(findings) == 1

    def test_module_alias_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_unit_test(
            tmp_charm,
            """\
            from ops import testing

            def test_charm():
                harness = testing.Harness(MyCharm)
            """,
        )
        assert len(findings) == 1

    def test_annotation_only_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_unit_test(
            tmp_charm,
            """\
            from ops.testing import Harness

            def test_charm(harness: Harness):
                assert harness
            """,
        )
        assert len(findings) == 1

    def test_scenario_api_not_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_unit_test(
            tmp_charm,
            """\
            import ops.testing

            def test_charm():
                ctx = ops.testing.Context(MyCharm)
                ctx.run(ctx.on.start(), ops.testing.State())
            """,
        )
        assert not findings

    def test_unrelated_local_harness_class_not_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_unit_test(
            tmp_charm,
            """\
            class Harness:
                pass

            def test_charm():
                assert Harness()
            """,
        )
        assert not findings

    def test_no_unit_tests_no_diagnostic(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test-charm"})
        report = lint(tmp_charm)
        assert _RULE not in {d.rule_id for d in report}

    def test_one_finding_per_module(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test-charm"})
        _write(tmp_charm, "tests/unit/test_charm.py", _HARNESS_TEST)
        _write(tmp_charm, "tests/unit/test_workload.py", _HARNESS_TEST)
        report = lint(tmp_charm)
        findings = [d for d in report if d.rule_id == _RULE]
        assert {d.path for d in findings} == {
            "tests/unit/test_charm.py",
            "tests/unit/test_workload.py",
        }

    def test_repeated_use_in_one_module_reported_once(self, tmp_charm: pathlib.Path):
        findings = _lint_unit_test(
            tmp_charm,
            """\
            from ops.testing import Harness

            def test_one():
                Harness(MyCharm).begin()

            def test_two():
                Harness(MyCharm).begin()
            """,
        )
        assert len(findings) == 1
        assert findings[0].line == 4

    def test_flat_test_layout_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test-charm"})
        _write(tmp_charm, "tests/test_charm.py", _HARNESS_TEST)
        report = lint(tmp_charm)
        findings = [d for d in report if d.rule_id == _RULE]
        assert len(findings) == 1
        assert findings[0].path == "tests/test_charm.py"

    def test_shared_conftest_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test-charm"})
        _write(tmp_charm, "tests/conftest.py", _HARNESS_TEST)
        report = lint(tmp_charm)
        findings = [d for d in report if d.rule_id == _RULE]
        assert len(findings) == 1
        assert findings[0].path == "tests/conftest.py"

    def test_charm_source_not_scanned(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test-charm"})
        _write(tmp_charm, "src/charm.py", _HARNESS_TEST)
        report = lint(tmp_charm)
        assert _RULE not in {d.rule_id for d in report}

    def test_vendored_library_not_scanned(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test-charm"})
        _write(tmp_charm, "lib/charms/other/v0/thing.py", _HARNESS_TEST)
        report = lint(tmp_charm)
        assert _RULE not in {d.rule_id for d in report}

    def test_integration_tests_not_scanned(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test-charm"})
        _write(tmp_charm, "tests/integration/test_charm.py", _HARNESS_TEST)
        report = lint(tmp_charm)
        assert _RULE not in {d.rule_id for d in report}


def _ops_scenario_findings(charm_dir: pathlib.Path, files: dict[str, str]):
    """Lint a charm made of *files*, returning its TESTING-004 findings."""
    write_charmcraft_yaml(charm_dir, {"name": "test-charm"})
    for relative, source in files.items():
        _write(charm_dir, relative, source)
    return [d for d in lint(charm_dir) if d.rule_id == "TESTING-004"]


class TestUsesOpsScenario:
    """TESTING-004 — tests depend on ops[testing], not ops-scenario."""

    def test_import_flagged(self, tmp_charm: pathlib.Path):
        findings = _ops_scenario_findings(
            tmp_charm,
            {
                "tests/unit/test_charm.py": """\
                import pytest
                import scenario

                def test_charm():
                    scenario.Context(MyCharm)
                """
            },
        )
        assert len(findings) == 1
        assert findings[0].severity == Severity.WARNING
        assert findings[0].path == "tests/unit/test_charm.py"
        assert findings[0].line == 2
        assert "ops.testing" in findings[0].message

    def test_from_submodule_import_flagged(self, tmp_charm: pathlib.Path):
        findings = _ops_scenario_findings(
            tmp_charm,
            {"tests/unit/test_charm.py": "from scenario.state import State\n"},
        )
        assert len(findings) == 1
        assert findings[0].line == 1

    def test_function_level_import_flagged(self, tmp_charm: pathlib.Path):
        findings = _ops_scenario_findings(
            tmp_charm,
            {
                "tests/unit/test_charm.py": """\
                def test_charm():
                    from scenario import Context
                """
            },
        )
        assert len(findings) == 1
        assert findings[0].line == 2

    def test_one_finding_per_module_at_first_import(self, tmp_charm: pathlib.Path):
        findings = _ops_scenario_findings(
            tmp_charm,
            {
                "tests/unit/test_charm.py": """\
                from scenario import Context

                from scenario.errors import UncaughtCharmError
                """,
                "tests/scenario/test_relations.py": "import scenario\n",
            },
        )
        assert {(d.path, d.line) for d in findings} == {
            ("tests/unit/test_charm.py", 1),
            ("tests/scenario/test_relations.py", 1),
        }

    def test_ops_testing_not_flagged(self, tmp_charm: pathlib.Path):
        findings = _ops_scenario_findings(
            tmp_charm,
            {
                "tests/unit/test_charm.py": """\
                import ops.testing
                from ops import testing
                from ops.testing import Context, State
                """
            },
        )
        assert not findings

    def test_similarly_named_module_not_flagged(self, tmp_charm: pathlib.Path):
        findings = _ops_scenario_findings(
            tmp_charm,
            {
                "tests/unit/test_charm.py": """\
                import scenarios
                from my_scenario import thing
                from . import scenario
                from .scenario import helper
                """
            },
        )
        assert not findings

    def test_charm_source_and_integration_tests_not_scanned(self, tmp_charm: pathlib.Path):
        findings = _ops_scenario_findings(
            tmp_charm,
            {
                "src/charm.py": "import scenario\n",
                "tests/integration/test_charm.py": "import scenario\n",
            },
        )
        assert not findings

    def test_pyproject_declarations_flagged(self, tmp_charm: pathlib.Path):
        findings = _ops_scenario_findings(
            tmp_charm,
            {
                "pyproject.toml": """\
                [project]
                dependencies = ["ops>=2.17"]

                [project.optional-dependencies]
                dev = ["pytest", "ops-scenario>=7"]

                [dependency-groups]
                unit = ["Ops_Scenario"]
                lint = ["ops[testing]"]
                """
            },
        )
        assert len(findings) == 1
        assert findings[0].path == "pyproject.toml"
        assert findings[0].line is None
        assert "`project.optional-dependencies.dev`" in findings[0].message
        assert "`dependency-groups.unit`" in findings[0].message
        assert "lint" not in findings[0].message

    def test_poetry_declaration_flagged(self, tmp_charm: pathlib.Path):
        findings = _ops_scenario_findings(
            tmp_charm,
            {
                "pyproject.toml": """\
                [tool.poetry.group.unit.dependencies]
                ops-scenario = "^7.0"
                """
            },
        )
        assert len(findings) == 1
        assert "`tool.poetry.group.unit.dependencies`" in findings[0].message

    @pytest.mark.parametrize(
        ("pyproject", "section"),
        [
            ('[project]\ndependencies = ["ops-scenario"]\n', "project.dependencies"),
            (
                '[tool.poetry.dev-dependencies]\nops_scenario = "*"\n',
                "tool.poetry.dev-dependencies",
            ),
            (
                '[tool.poetry.dependencies]\n"Ops.Scenario" = "^7"\n',
                "tool.poetry.dependencies",
            ),
        ],
    )
    def test_pyproject_layout_flagged(self, tmp_charm: pathlib.Path, pyproject: str, section: str):
        findings = _ops_scenario_findings(tmp_charm, {"pyproject.toml": pyproject})
        assert len(findings) == 1
        assert f"`{section}`" in findings[0].message

    def test_pyproject_without_it_not_flagged(self, tmp_charm: pathlib.Path):
        findings = _ops_scenario_findings(
            tmp_charm,
            {
                "pyproject.toml": """\
                [project]
                dependencies = ["ops>=2.17", "ops-scenario-helpers"]

                [dependency-groups]
                unit = ["ops[testing]>=2.17", {include-group = "lint"}]
                lint = ["pytest-scenario"]

                [tool.poetry.group.unit.dependencies]
                ops = {version = "^2.17", extras = ["testing"]}
                """
            },
        )
        assert not findings

    def test_requirements_file_flagged(self, tmp_charm: pathlib.Path):
        findings = _ops_scenario_findings(
            tmp_charm,
            {
                "requirements-dev.txt": """\
                # unit test dependencies
                pytest
                ops-scenario==6.1.7  # for the state-transition tests
                """
            },
        )
        assert len(findings) == 1
        assert findings[0].path == "requirements-dev.txt"
        assert findings[0].line == 3

    def test_requirements_in_file_flagged(self, tmp_charm: pathlib.Path):
        findings = _ops_scenario_findings(
            tmp_charm, {"test-requirements.in": "pytest\nops-scenario\n"}
        )
        assert [(d.path, d.line) for d in findings] == [("test-requirements.in", 2)]

    def test_compiled_requirements_file_not_flagged(self, tmp_charm: pathlib.Path):
        findings = _ops_scenario_findings(
            tmp_charm,
            {
                "requirements-unit.txt": """\
                # This file was autogenerated by uv via the following command:
                #    uv pip compile pyproject.toml --group=unit
                ops==2.17.0
                    # via ops-scenario
                ops-scenario==7.0.5
                    # via ops
                """
            },
        )
        assert not findings

    def test_tox_ini_deps_flagged(self, tmp_charm: pathlib.Path):
        findings = _ops_scenario_findings(
            tmp_charm,
            {
                "tox.ini": """\
                [testenv:lint]
                ; ops-scenario
                commands = pip install ops-scenario

                [testenv:unit]
                deps =
                    pytest
                    # ops-scenario
                    unit: ops-scenario==7.0  # factor-conditional
                commands = pytest
                """
            },
        )
        assert len(findings) == 1
        assert findings[0].path == "tox.ini"
        assert findings[0].line == 9

    def test_tox_ini_single_line_deps_flagged(self, tmp_charm: pathlib.Path):
        findings = _ops_scenario_findings(
            tmp_charm,
            {"tox.ini": "[testenv:unit]\ndeps = ops-scenario\n"},
        )
        assert [d.line for d in findings] == [2]

    def test_tox_ini_other_keys_not_flagged(self, tmp_charm: pathlib.Path):
        findings = _ops_scenario_findings(
            tmp_charm,
            {"tox.ini": "[testenv:unit]\nsetenv =\n    ops-scenario=1\ndeps = pytest\n"},
        )
        assert not findings

    def test_tox_ini_colon_without_space_is_not_a_factor(self, tmp_charm: pathlib.Path):
        # tox passes ``unit:ops-scenario`` to the installer whole, so the
        # requirement it names is ``unit``, not ``ops-scenario``.
        findings = _ops_scenario_findings(
            tmp_charm, {"tox.ini": "[testenv:unit]\ndeps = unit:ops-scenario\n"}
        )
        assert not findings

    def test_tox_toml_deps_flagged(self, tmp_charm: pathlib.Path):
        findings = _ops_scenario_findings(
            tmp_charm,
            {
                "tox.toml": """\
                [env_run_base]
                deps = ["pytest"]

                [env.unit]
                deps = ["pytest", "ops-scenario==8.8.0", "-r requirements.txt"]
                """
            },
        )
        assert len(findings) == 1
        assert findings[0].path == "tox.toml"
        assert "`env.unit.deps`" in findings[0].message

    def test_tox_toml_env_run_base_flagged(self, tmp_charm: pathlib.Path):
        findings = _ops_scenario_findings(
            tmp_charm, {"tox.toml": '[env_run_base]\ndeps = ["ops-scenario"]\n'}
        )
        assert len(findings) == 1
        assert "`env_run_base.deps`" in findings[0].message

    def test_broken_tox_toml_not_flagged(self, tmp_charm: pathlib.Path):
        findings = _ops_scenario_findings(tmp_charm, {"tox.toml": "[env.unit\n"})
        assert not findings

    def test_declaration_and_import_both_reported(self, tmp_charm: pathlib.Path):
        findings = _ops_scenario_findings(
            tmp_charm,
            {
                "requirements-dev.txt": "ops-scenario\n",
                "tests/unit/test_charm.py": "import scenario\n",
            },
        )
        assert {d.path for d in findings} == {"requirements-dev.txt", "tests/unit/test_charm.py"}
