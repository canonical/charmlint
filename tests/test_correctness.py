"""Tests for CORRECTNESS-### rules."""

import pathlib
import textwrap
from typing import Any

from charmlint._linter import lint
from charmlint._models import Severity
from tests.conftest import write_charm_source, write_charmcraft_yaml


def _lint_source(
    charm_dir: pathlib.Path,
    source: str,
    metadata: dict[str, Any] | None = None,
):
    """Lint a charm with the given src/charm.py, returning CORRECTNESS-009 findings."""
    if metadata is not None:
        write_charmcraft_yaml(charm_dir, {"name": "test", **metadata})
    write_charm_source(charm_dir, textwrap.dedent(source))
    report = lint(charm_dir)
    return [d for d in report if d.rule_id == "CORRECTNESS-009"]


_CONTAINERS = {"containers": {"workload": {"resource": "workload-image"}}}


def _charm(body: str) -> str:
    """A charm whose ``_reconcile`` body is *body*."""
    return "import ops\n\nclass C(ops.CharmBase):\n    def _reconcile(self):\n" + textwrap.indent(
        textwrap.dedent(body), " " * 8
    )


class TestContainerNameMismatch:
    """CORRECTNESS-009 — get_container() must name a declared container."""

    def test_declared_name_not_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm, _charm('self.unit.get_container("workload")'), _CONTAINERS
        )
        assert not findings

    def test_undeclared_name_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_source(tmp_charm, _charm('self.unit.get_container("test")'), _CONTAINERS)
        assert len(findings) == 1
        assert findings[0].severity == Severity.ERROR
        assert "'test'" in findings[0].message
        assert "'workload'" in findings[0].message
        assert findings[0].path == "src/charm.py"
        assert findings[0].line == 5

    def test_keyword_argument_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _charm('self.unit.get_container(container_name="test")'),
            _CONTAINERS,
        )
        assert len(findings) == 1

    def test_no_containers_declared_ignored(self, tmp_charm: pathlib.Path):
        """A charm declaring no containers builds them somewhere charmlint can't see."""
        findings = _lint_source(tmp_charm, _charm('self.unit.get_container("workload")'), {})
        assert not findings

    def test_charmcraft_extension_ignored(self, tmp_charm: pathlib.Path):
        """An extension injects containers that never appear in charmcraft.yaml."""
        findings = _lint_source(
            tmp_charm,
            _charm('self.unit.get_container("app")'),
            {"extensions": ["go-framework"], **_CONTAINERS},
        )
        assert not findings

    def test_every_call_reported(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _charm("""\
                self.unit.get_container("one")
                self.model.unit.get_container("two")
            """),
            _CONTAINERS,
        )
        assert len(findings) == 2
        assert [f.line for f in findings] == [5, 6]

    def test_non_literal_name_ignored(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _charm("""\
                for name in self.meta.containers:
                    self.unit.get_container(name)
                self.unit.get_container(f"{self.app.name}-workload")
                self.unit.get_container(self.config["container"])
            """),
            _CONTAINERS,
        )
        assert not findings

    def test_unrelated_calls_ignored(self, tmp_charm: pathlib.Path):
        findings = _lint_source(
            tmp_charm,
            _charm("""\
                self.unit.get_container()
                helper("nginx")
            """),
            _CONTAINERS,
        )
        assert not findings

    def test_no_metadata_is_fatal_not_a_finding(self, tmp_charm: pathlib.Path):
        """A directory with no metadata at all is not a charm to report on."""
        findings = _lint_source(tmp_charm, _charm('self.unit.get_container("workload")'))
        assert not findings

    def test_owned_library_ignored(self, tmp_charm: pathlib.Path):
        """A library this charm publishes runs inside other charms."""
        write_charmcraft_yaml(tmp_charm, {"name": "test", **_CONTAINERS})
        lib = tmp_charm / "lib" / "charms" / "test" / "v0"
        lib.mkdir(parents=True)
        (lib / "helper.py").write_text('def f(unit):\n    unit.get_container("other")\n')
        write_charm_source(tmp_charm, "import ops\n")
        report = lint(tmp_charm)
        assert not [d for d in report if d.rule_id == "CORRECTNESS-009"]

    def test_tests_ignored(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test", **_CONTAINERS})
        write_charm_source(tmp_charm, "import ops\n")
        unit = tmp_charm / "tests" / "unit"
        unit.mkdir(parents=True)
        (unit / "test_charm.py").write_text('def test_x(unit):\n    unit.get_container("other")\n')
        report = lint(tmp_charm)
        assert not [d for d in report if d.rule_id == "CORRECTNESS-009"]
