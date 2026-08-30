"""Tests for PERFORMANCE-### rules."""

import pathlib
import textwrap

from charmlint._linter import lint
from charmlint._models import Severity
from tests.conftest import write_charm_source, write_charmcraft_yaml


def _lint_source(charm_dir: pathlib.Path, source: str):
    """Lint a charm whose src/charm.py is *source*, returning the findings."""
    write_charmcraft_yaml(charm_dir, {"name": "test"})
    write_charm_source(charm_dir, textwrap.dedent(source))
    report = lint(charm_dir)
    return [d for d in report if d.rule_id == "PERFORMANCE-002"]


class TestRepeatedPebbleState:
    """PERFORMANCE-002 — the same Pebble read made twice in one function."""

    def test_repeated_get_service_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            """\
            def _reconcile(self, container):
                if not container.get_service("app").is_running():
                    self.log("down")
                self.report(container.get_service("app").current)
            """,
        )
        assert len(findings) == 1
        assert findings[0].severity == Severity.INFO
        assert "container.get_service('app')" in findings[0].message
        assert "_reconcile" in findings[0].message
        assert findings[0].path == "src/charm.py"
        assert findings[0].line == 4

    def test_repeated_get_plan_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            """\
            def _reconcile(self, container):
                services = container.get_plan().services
                checks = container.get_plan().checks
                return services, checks
            """,
        )
        assert len(findings) == 1
        assert "container.get_plan()" in findings[0].message
        assert "line 2" in findings[0].message
        assert findings[0].line == 3

    def test_attribute_receiver_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            """\
            class C:
                def _reconcile(self):
                    a = self._container.get_plan()
                    b = self._container.get_plan()
                    return a, b
            """,
        )
        assert len(findings) == 1
        assert "self._container.get_plan()" in findings[0].message

    def test_three_calls_report_each_repeat(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            """\
            def _reconcile(self, container):
                a = container.get_plan()
                b = container.get_plan()
                c = container.get_plan()
                return a, b, c
            """,
        )
        assert [d.line for d in findings] == [3, 4]

    def test_single_call_clean(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            """\
            def _reconcile(self, container):
                plan = container.get_plan()
                return plan.services, plan.checks
            """,
        )
        assert findings == []

    def test_different_services_clean(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            """\
            def _reconcile(self, container):
                a = container.get_service("app")
                b = container.get_service("worker")
                return a, b
            """,
        )
        assert findings == []

    def test_different_receivers_clean(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            """\
            def _reconcile(self, app_container, worker_container):
                a = app_container.get_plan()
                b = worker_container.get_plan()
                return a, b
            """,
        )
        assert findings == []

    def test_computed_service_name_clean(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            """\
            def _reconcile(self, container, name, other):
                a = container.get_service(name)
                b = container.get_service(other)
                return a, b
            """,
        )
        assert findings == []

    def test_unreadable_receiver_clean(self, tmp_charm: pathlib.Path):
        """A receiver that is itself a call is not known to be the same object."""
        findings = _lint_source(
            tmp_charm,
            """\
            class C:
                def _reconcile(self):
                    a = self.unit.get_container("w").get_plan()
                    b = self.unit.get_container("w").get_plan()
                    return a, b
            """,
        )
        assert findings == []

    def test_separate_functions_clean(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            """\
            class C:
                def _one(self, container):
                    return container.get_plan()

                def _two(self, container):
                    return container.get_plan()
            """,
        )
        assert findings == []

    def test_nested_function_is_its_own_scope(self, tmp_charm: pathlib.Path):
        """A call in a closure runs per call of the closure, not per outer call."""
        findings = _lint_source(
            tmp_charm,
            """\
            def _reconcile(self, container):
                def ready():
                    return container.get_plan().services

                self.wait(ready)
                return container.get_plan()
            """,
        )
        assert findings == []

    def test_nested_function_repeat_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            """\
            def _reconcile(self, container):
                def ready():
                    return container.get_plan().services and container.get_plan().checks

                return ready
            """,
        )
        assert len(findings) == 1
        assert "'ready'" in findings[0].message

    def test_alternative_if_branches_clean(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            """\
            def _reconcile(self, container, flag):
                if flag:
                    plan = container.get_plan()
                else:
                    plan = container.get_plan()
                return plan
            """,
        )
        assert findings == []

    def test_alternative_match_cases_clean(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            """\
            def _reconcile(self, container, mode):
                match mode:
                    case "a":
                        plan = container.get_plan()
                    case _:
                        plan = container.get_plan()
                return plan
            """,
        )
        assert findings == []

    def test_branch_and_following_statement_flagged(self, tmp_charm: pathlib.Path):
        """One arm of an ``if`` and the code after it do both run."""
        findings = _lint_source(
            tmp_charm,
            """\
            def _reconcile(self, container, flag):
                if flag:
                    self.log(container.get_plan())
                return container.get_plan()
            """,
        )
        assert len(findings) == 1
        assert findings[0].line == 4

    def test_read_after_add_layer_clean(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            """\
            def _reconcile(self, container, layer):
                current = container.get_plan()
                container.add_layer("app", layer, combine=True)
                updated = container.get_plan()
                return current, updated
            """,
        )
        assert findings == []

    def test_constant_service_name_flagged(self, tmp_charm: pathlib.Path):
        """The service name is nearly always a constant rather than a literal."""
        findings = _lint_source(
            tmp_charm,
            """\
            SERVICE = "app"

            def _reconcile(self, container):
                if container.get_service(SERVICE).is_running():
                    self.log("up")
                return container.get_service(SERVICE)
            """,
        )
        assert len(findings) == 1
        assert "container.get_service(SERVICE)" in findings[0].message

    def test_literal_and_constant_names_are_distinct(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            """\
            SERVICE = "app"

            def _reconcile(self, container):
                a = container.get_service(SERVICE)
                b = container.get_service("SERVICE")
                return a, b
            """,
        )
        assert findings == []

    def test_receiver_not_named_like_a_container_clean(self, tmp_charm: pathlib.Path):
        """``get_service`` is a common method name on unrelated API clients."""
        findings = _lint_source(
            tmp_charm,
            """\
            def _create(self, ranger, name):
                existing = ranger.get_service(name)
                if existing is not None:
                    return existing
                ranger.create_service(name)
                return ranger.get_service(name)
            """,
        )
        assert findings == []

    def test_get_plan_survives_a_restart(self, tmp_charm: pathlib.Path):
        """Restarting a service does not change the plan that describes it."""
        findings = _lint_source(
            tmp_charm,
            """\
            def _restart(self, container, name):
                if not container.get_plan().services.get(name):
                    return False
                container.restart(name)
                plan = container.get_plan()
                return plan.services.get(name)
            """,
        )
        assert len(findings) == 1
        assert findings[0].line == 5

    def test_read_after_restart_clean(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            """\
            def _reconcile(self, container):
                before = container.get_service("app")
                container.restart("app")
                after = container.get_service("app")
                return before, after
            """,
        )
        assert findings == []

    def test_mutation_of_another_container_still_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            """\
            def _reconcile(self, container, other_container, layer):
                a = container.get_plan()
                other_container.add_layer("app", layer, combine=True)
                b = container.get_plan()
                return a, b
            """,
        )
        assert len(findings) == 1

    def test_read_after_rebinding_the_receiver_clean(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            """\
            class C:
                def _reconcile(self):
                    container = self.unit.get_container("first")
                    a = container.get_plan()
                    container = self.unit.get_container("second")
                    b = container.get_plan()
                    return a, b
            """,
        )
        assert findings == []

    def test_repeat_in_a_loop_body_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            """\
            def _reconcile(self, container, names):
                for name in names:
                    self.log(container.get_plan().services)
                    self.log(container.get_plan().checks)
            """,
        )
        assert len(findings) == 1

    def test_try_body_and_handler_flagged(self, tmp_charm: pathlib.Path):
        """A handler runs after part of the body, so both calls can be made."""
        findings = _lint_source(
            tmp_charm,
            """\
            def _reconcile(self, container):
                try:
                    return container.get_plan()
                except Exception:
                    self.log("retrying")
                    return container.get_plan()
            """,
        )
        assert len(findings) == 1

    def test_annotated_rebinding_clean(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            """\
            import ops

            class C(ops.CharmBase):
                def _reconcile(self):
                    container: ops.Container = self.unit.get_container("first")
                    a = container.get_plan()
                    container: ops.Container = self.unit.get_container("second")
                    b = container.get_plan()
                    return a, b
            """,
        )
        assert findings == []

    def test_unexpected_arguments_clean(self, tmp_charm: pathlib.Path):
        """Neither call has the signature of the ops method, so neither is one."""
        findings = _lint_source(
            tmp_charm,
            """\
            def _reconcile(self, container):
                a = container.get_service("app", "extra")
                b = container.get_service("app", "extra")
                c = container.get_service("app", timeout=5)
                d = container.get_service("app", timeout=5)
                e = container.get_plan("app")
                f = container.get_plan("app")
                return a, b, c, d, e, f
            """,
        )
        assert findings == []

    def test_unrelated_methods_clean(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            """\
            def _reconcile(self, container):
                a = container.get_services()
                b = container.get_services()
                c = container.get_checks("up")
                d = container.get_checks("up")
                return a, b, c, d
            """,
        )
        assert findings == []

    def test_vendored_lib_skipped(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        lib_dir = tmp_charm / "lib" / "charms" / "someone" / "v0"
        lib_dir.mkdir(parents=True)
        (lib_dir / "helper.py").write_text(
            textwrap.dedent("""\
                def check(container):
                    return container.get_plan(), container.get_plan()
            """)
        )
        report = lint(tmp_charm)
        assert "PERFORMANCE-002" not in {d.rule_id for d in report}

    def test_own_published_lib_checked(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "my-charm"})
        lib_dir = tmp_charm / "lib" / "charms" / "my_charm" / "v0"
        lib_dir.mkdir(parents=True)
        (lib_dir / "helper.py").write_text(
            textwrap.dedent("""\
                def check(container):
                    return container.get_plan(), container.get_plan()
            """)
        )
        findings = [d for d in lint(tmp_charm) if d.rule_id == "PERFORMANCE-002"]
        assert len(findings) == 1
        assert findings[0].path == "lib/charms/my_charm/v0/helper.py"

    def test_tests_not_checked(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        unit = tmp_charm / "tests" / "unit"
        unit.mkdir(parents=True)
        (unit / "test_charm.py").write_text(
            textwrap.dedent("""\
                def test_plan(container):
                    assert container.get_plan() == container.get_plan()
            """)
        )
        assert "PERFORMANCE-002" not in {d.rule_id for d in lint(tmp_charm)}
