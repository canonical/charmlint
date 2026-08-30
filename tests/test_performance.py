"""Tests for PERFORMANCE-### rules."""

import pathlib
import textwrap

from charmlint._linter import lint
from charmlint._models import Severity
from tests.conftest import write_charm_source, write_charmcraft_yaml


def _lint_source(charm_dir: pathlib.Path, source: str):
    """Lint a charm whose src/charm.py is *source*, returning PERFORMANCE-001 findings."""
    write_charmcraft_yaml(charm_dir, {"name": "test"})
    write_charm_source(charm_dir, textwrap.dedent(source))
    report = lint(charm_dir)
    return [d for d in report if d.rule_id == "PERFORMANCE-001"]


def _method(body: str) -> str:
    """A charm class with *body* as the body of a single method."""
    return "import ops\n\nclass C(ops.CharmBase):\n    def _configure(self):\n" + textwrap.indent(
        textwrap.dedent(body), " " * 8
    )


class TestRepeatedConfigAccess:
    """PERFORMANCE-001 — the same config option read repeatedly in one function."""

    def test_three_subscripts_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _method("""\
                a = self.config['port']
                b = self.config['port']
                c = self.config['port']
                return a, b, c
            """),
        )
        assert len(findings) == 1
        assert findings[0].severity == Severity.INFO
        assert "'port'" in findings[0].message
        assert "_configure" in findings[0].message
        assert findings[0].path == "src/charm.py"
        # Anchored at the ``def`` line, not at any one of the reads.
        assert findings[0].line == 4

    def test_three_get_calls_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _method("""\
                a = self.config.get('port')
                b = self.config.get('port', 80)
                c = self.config.get('port')
                return a, b, c
            """),
        )
        assert len(findings) == 1

    def test_mixed_spellings_count_together(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _method("""\
                a = self.config['port']
                b = self.config.get('port')
                c = self.config['port']
                return a, b, c
            """),
        )
        assert len(findings) == 1

    def test_two_reads_not_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _method("""\
                if self.config['port']:
                    return self.config['port']
                return None
            """),
        )
        assert findings == []

    def test_different_options_not_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _method("""\
                a = self.config['port']
                b = self.config['host']
                c = self.config['user']
                return a, b, c
            """),
        )
        assert findings == []

    def test_reads_in_different_functions_not_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            """\
            import ops

            class C(ops.CharmBase):
                def a(self):
                    return self.config['port']

                def b(self):
                    return self.config['port']

                def c(self):
                    return self.config['port']
            """,
        )
        assert findings == []

    def test_one_diagnostic_per_option(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _method("""\
                a = self.config['port'], self.config['port'], self.config['port']
                b = self.config['host'], self.config['host'], self.config['host']
                return a, b
            """),
        )
        assert len(findings) == 2
        assert {f.message.split("'")[1] for f in findings} == {"port", "host"}

    def test_count_reported_in_message(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _method("""\
                return (
                    self.config['port'],
                    self.config['port'],
                    self.config['port'],
                    self.config['port'],
                )
            """),
        )
        assert len(findings) == 1
        assert "read 4 times" in findings[0].message

    def test_library_receiver_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            """\
            class Requirer:
                def _emit(self):
                    a = self.charm.config['port']
                    b = self.charm.config['port']
                    c = self.charm.config['port']
                    return a, b, c
            """,
        )
        assert len(findings) == 1
        assert "self.charm.config['port']" in (findings[0].fix_hint or "")

    def test_distinct_receivers_counted_separately(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _method("""\
                a = self.config['port']
                b = self.config['port']
                c = self.charm.config['port']
                d = self.charm.config['port']
                return a, b, c, d
            """),
        )
        assert findings == []

    def test_unrelated_config_attribute_not_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _method("""\
                a = parser.config['port']
                b = parser.config['port']
                c = parser.config['port']
                return a, b, c
            """),
        )
        assert findings == []

    def test_stored_state_copy_of_config_not_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _method("""\
                a = self._stored.config['port']
                b = self._stored.config['port']
                c = self._stored.config['port']
                return a, b, c
            """),
        )
        assert findings == []

    def test_non_literal_key_not_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _method("""\
                a = self.config[name]
                b = self.config[name]
                c = self.config[name]
                return a, b, c
            """),
        )
        assert findings == []

    def test_get_without_arguments_not_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _method("""\
                a = self.config.get()
                b = self.config.get()
                c = self.config.get()
                return a, b, c
            """),
        )
        assert findings == []

    def test_exclusive_if_branches_not_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _method("""\
                if self.model.unit.is_leader():
                    return self.config['mode']
                elif self.stored.ready:
                    return self.config['mode']
                else:
                    return self.config['mode']
            """),
        )
        assert findings == []

    def test_read_before_exclusive_branches_counted_once(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _method("""\
                mode = self.config['mode']
                if mode:
                    return self.config['mode'], 1
                return self.config['mode'], 2
            """),
        )
        assert findings == []

    def test_three_reads_in_one_branch_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _method("""\
                if self.model.unit.is_leader():
                    return self.config['mode'], self.config['mode'], self.config['mode']
                return None
            """),
        )
        assert len(findings) == 1

    def test_exclusive_match_cases_not_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _method("""\
                match self.mode:
                    case 'a':
                        return self.config['level']
                    case 'b':
                        return self.config['level']
                    case _:
                        return self.config['level']
            """),
        )
        assert findings == []

    def test_exclusive_except_handlers_not_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _method("""\
                try:
                    return self.config['level']
                except KeyError:
                    return self.config['level']
                except ValueError:
                    return self.config['level']
            """),
        )
        assert findings == []

    def test_finally_runs_after_either_path(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _method("""\
                try:
                    a = self.config['level']
                except KeyError:
                    a = None
                finally:
                    b = self.config['level']
                    c = self.config['level']
                return a, b, c
            """),
        )
        assert len(findings) == 1

    def test_conditional_expression_arms_not_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _method("""\
                a = self.config['n'] if self.flag else self.config['n']
                b = self.config['n'] if self.flag else self.config['n']
                return a, b
            """),
        )
        assert findings == []

    def test_loop_body_counted_once(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _method("""\
                for item in self.items:
                    print(item, self.config['level'])
                while self.running:
                    print(self.config['level'])
            """),
        )
        assert findings == []

    def test_reads_in_nested_function_not_counted_in_parent(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _method("""\
                level = self.config['level']

                def inner():
                    return self.config['level'], self.config['level']

                return level, inner
            """),
        )
        assert findings == []

    def test_nested_function_flagged_on_its_own(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _method("""\
                def inner():
                    a = self.config['level']
                    b = self.config['level']
                    c = self.config['level']
                    return a, b, c

                return inner
            """),
        )
        assert len(findings) == 1
        assert "'inner'" in findings[0].message

    def test_lambda_body_not_counted_in_parent(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _method("""\
                a = self.config['level']
                b = lambda: self.config['level']
                c = lambda: self.config['level']
                return a, b, c
            """),
        )
        assert findings == []

    def test_comprehension_counted_once(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _method("""\
                return [x for x in self.items if x == self.config['level']]
            """),
        )
        assert findings == []

    def test_module_level_code_not_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            """\
            a = self.config['level']
            b = self.config['level']
            c = self.config['level']
            """,
        )
        assert findings == []

    def test_vendored_library_not_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        vendored = tmp_charm / "lib" / "charms" / "other_charm" / "v0"
        vendored.mkdir(parents=True)
        (vendored / "thing.py").write_text(
            textwrap.dedent("""\
                class Requirer:
                    def _emit(self):
                        a = self.charm.config['port']
                        b = self.charm.config['port']
                        c = self.charm.config['port']
                        return a, b, c
            """)
        )
        report = lint(tmp_charm)
        assert [d for d in report if d.rule_id == "PERFORMANCE-001"] == []

    def test_owned_library_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test-charm"})
        owned = tmp_charm / "lib" / "charms" / "test_charm" / "v0"
        owned.mkdir(parents=True)
        (owned / "thing.py").write_text(
            textwrap.dedent("""\
                class Requirer:
                    def _emit(self):
                        a = self.charm.config['port']
                        b = self.charm.config['port']
                        c = self.charm.config['port']
                        return a, b, c
            """)
        )
        report = lint(tmp_charm)
        assert len([d for d in report if d.rule_id == "PERFORMANCE-001"]) == 1

    def test_tests_not_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        unit = tmp_charm / "tests" / "unit"
        unit.mkdir(parents=True)
        (unit / "test_charm.py").write_text(
            textwrap.dedent("""\
                def test_config(self):
                    a = self.config['port']
                    b = self.config['port']
                    c = self.config['port']
                    return a, b, c
            """)
        )
        report = lint(tmp_charm)
        assert [d for d in report if d.rule_id == "PERFORMANCE-001"] == []
