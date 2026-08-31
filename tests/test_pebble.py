"""Tests for PEBBLE-### rules."""

import pathlib
import textwrap

from charmlint._linter import lint
from charmlint._models import Severity
from tests.conftest import write_charm_source, write_charmcraft_yaml


def _lint_source(charm_dir: pathlib.Path, source: str):
    """Lint a charm whose src/charm.py is *source*, returning PEBBLE-005 findings."""
    write_charmcraft_yaml(charm_dir, {"name": "test"})
    write_charm_source(charm_dir, textwrap.dedent(source))
    report = lint(charm_dir)
    return [d for d in report if d.rule_id == "PEBBLE-005"]


def _layer(environment: str) -> str:
    """A charm source defining a Pebble layer with the given environment body.

    *environment* is the dict body alone, written without indentation; it
    is indented here to the depth the layer needs.
    """
    body = textwrap.indent(textwrap.dedent(environment), " " * 24)
    return f"""\
        import ops

        class C(ops.CharmBase):
            @property
            def _pebble_layer(self):
                return ops.pebble.Layer({{
                    "summary": "workload",
                    "services": {{
                        "workload": {{
                            "override": "replace",
                            "command": "/bin/workload",
                            "environment": {{
{body}
                            }},
                        }},
                    }},
                }})
    """


class TestPebbleEnvNonString:
    """PEBBLE-005 — environment values in a Pebble layer must be strings."""

    def test_none_value_flagged_as_error(self, tmp_charm: pathlib.Path):
        findings = _lint_source(tmp_charm, _layer('"PROXY": None,'))
        assert len(findings) == 1
        assert findings[0].severity == Severity.ERROR
        assert "PROXY" in findings[0].message
        assert findings[0].path is not None
        assert findings[0].line is not None

    def test_bool_value_flagged_as_info(self, tmp_charm: pathlib.Path):
        findings = _lint_source(tmp_charm, _layer('"DEBUG": True,'))
        assert len(findings) == 1
        assert findings[0].severity == Severity.INFO
        assert "DEBUG" in findings[0].message
        assert "'true'" in findings[0].message

    def test_int_value_flagged_as_info(self, tmp_charm: pathlib.Path):
        findings = _lint_source(tmp_charm, _layer('"PORT": 8080,'))
        assert len(findings) == 1
        assert findings[0].severity == Severity.INFO
        assert "PORT" in findings[0].message

    def test_float_value_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_source(tmp_charm, _layer('"RATIO": 0.5,'))
        assert len(findings) == 1
        assert findings[0].severity == Severity.INFO

    def test_string_values_not_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _layer('"PORT": "8080",\n"DEBUG": "true",\n"EMPTY": "",'),
        )
        assert findings == []

    def test_computed_values_not_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _layer(
                '"PORT": str(self.config["port"]),\n'
                '"URL": f"http://{self.hostname}",\n'
                '"MODE": MODE,\n'
                '"OPT": self.config.get("opt"),'
            ),
        )
        assert findings == []

    def test_dict_unpacking_not_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_source(tmp_charm, _layer("**self._base_env,"))
        assert findings == []

    def test_multiple_values_each_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _layer('"PROXY": None,\n"DEBUG": False,\n"OK": "yes",'),
        )
        assert len(findings) == 2
        assert {d.severity for d in findings} == {Severity.ERROR, Severity.INFO}
        assert findings[0].line != findings[1].line

    def test_add_layer_call_form_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            """\
                import ops

                class C(ops.CharmBase):
                    def _reconcile(self, container):
                        container.add_layer(
                            "workload",
                            {
                                "services": {
                                    "workload": {
                                        "command": "/bin/workload",
                                        "environment": {"PROXY": None},
                                    },
                                },
                            },
                            combine=True,
                        )
            """,
        )
        assert len(findings) == 1
        assert findings[0].severity == Severity.ERROR

    def test_service_dict_built_separately_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            """\
                import ops

                class C(ops.CharmBase):
                    def _layer(self):
                        service = {
                            "override": "replace",
                            "command": "/bin/workload",
                            "environment": {"TRACING_ENABLED": False},
                        }
                        return ops.pebble.Layer({"services": {"workload": service}})
            """,
        )
        assert len(findings) == 1
        assert "TRACING_ENABLED" in findings[0].message

    def test_service_reported_once_when_nested_and_marked(self, tmp_charm: pathlib.Path):
        findings = _lint_source(tmp_charm, _layer('"PROXY": None,'))
        assert len(findings) == 1

    def test_exec_check_environment_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            """\
                import ops

                class C(ops.CharmBase):
                    def _layer(self):
                        return ops.pebble.Layer({
                            "checks": {
                                "up": {
                                    "override": "replace",
                                    "exec": {
                                        "command": "/bin/check",
                                        "environment": {"VERBOSE": True},
                                    },
                                },
                            },
                        })
            """,
        )
        assert len(findings) == 1
        assert "VERBOSE" in findings[0].message
        assert findings[0].severity == Severity.INFO

    def test_environment_outside_a_layer_not_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            """\
                import ops

                class C(ops.CharmBase):
                    def _run(self):
                        return subprocess.run(["x"], environment={"DEBUG": True})
            """,
        )
        assert findings == []

    def test_non_string_service_environment_key_not_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _layer("VAR_NAME: 1,"),
        )
        assert len(findings) == 1
        assert "an environment variable" in findings[0].message

    def test_vendored_lib_skipped(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        lib_dir = tmp_charm / "lib" / "charms" / "someone" / "v0"
        lib_dir.mkdir(parents=True)
        (lib_dir / "helper.py").write_text(
            textwrap.dedent("""\
                LAYER = {
                    "services": {
                        "workload": {"environment": {"PROXY": None}},
                    },
                }
            """)
        )
        report = lint(tmp_charm)
        assert "PEBBLE-005" not in {d.rule_id for d in report}

    def test_own_published_lib_checked(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "my-charm"})
        lib_dir = tmp_charm / "lib" / "charms" / "my_charm" / "v0"
        lib_dir.mkdir(parents=True)
        (lib_dir / "helper.py").write_text(
            textwrap.dedent("""\
                LAYER = {
                    "services": {
                        "workload": {"environment": {"PROXY": None}},
                    },
                }
            """)
        )
        report = lint(tmp_charm)
        findings = [d for d in report if d.rule_id == "PEBBLE-005"]
        assert len(findings) == 1
        assert findings[0].path == "lib/charms/my_charm/v0/helper.py"

    def test_syntax_error_is_fatal(self, tmp_charm: pathlib.Path):
        """A source that does not parse is reported by the core, not skipped here."""
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(tmp_charm, "def broken(:\n")
        assert [d.rule_id for d in lint(tmp_charm)] == ["FATAL"]
