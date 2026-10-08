"""Tests for TESTING-### rules."""

import pathlib
import textwrap

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
