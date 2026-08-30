"""Tests for FEATURES rules."""

import pathlib
import textwrap
from typing import Any

from charmlint._linter import lint
from charmlint._models import Severity
from tests.conftest import write_charm_source, write_charmcraft_yaml

_CONTAINERS: dict[str, Any] = {"workload": {"resource": "workload-image"}}

_PEBBLE_RULES = frozenset({"FEATURES-002", "FEATURES-003"})


def _lint(charm_dir: pathlib.Path, source: str, *, containers: bool = True):
    """Lint a charm whose src/charm.py is *source*, returning the Pebble findings."""
    metadata: dict[str, Any] = {"name": "test"}
    if containers:
        metadata["containers"] = _CONTAINERS
    write_charmcraft_yaml(charm_dir, metadata)
    write_charm_source(charm_dir, textwrap.dedent(source))
    report = lint(charm_dir)
    # FEATURES-004 fires on every charm here — none of them declare
    # `assumes` — so the Pebble rules are picked out by ID.
    return [d for d in report if d.rule_id in _PEBBLE_RULES]


_NO_CHECKS = """\
    import ops

    class C(ops.CharmBase):
        @property
        def _pebble_layer(self):
            return ops.pebble.Layer({
                "summary": "workload",
                "services": {
                    "workload": {"override": "replace", "command": "/bin/workload"},
                },
            })
"""

_CHECKS = """\
    import ops

    class C(ops.CharmBase):
        @property
        def _pebble_layer(self):
            return ops.pebble.Layer({
                "summary": "workload",
                "services": {
                    "workload": {"override": "replace", "command": "/bin/workload"},
                },
                "checks": {
                    "up": {
                        "override": "replace",
                        "level": "alive",
                        "http": {"url": "http://localhost:8080/health"},
                    },
                },
            })
"""


class TestMissingPebbleChecks:
    """FEATURES-002 — a charm with containers should define Pebble checks."""

    def test_containers_without_checks_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint(tmp_charm, _NO_CHECKS)
        assert [d.rule_id for d in findings] == ["FEATURES-002"]
        assert findings[0].severity == Severity.INFO
        assert findings[0].path == "src/charm.py"
        assert findings[0].line is not None

    def test_checks_defined_not_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint(tmp_charm, _CHECKS)
        assert "FEATURES-002" not in {d.rule_id for d in findings}

    def test_no_containers_not_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint(tmp_charm, _NO_CHECKS, containers=False)
        assert findings == []

    def test_check_api_call_suppresses(self, tmp_charm: pathlib.Path):
        """A charm driving checks at runtime has them, wherever they came from."""
        findings = _lint(
            tmp_charm,
            """\
                import ops

                class C(ops.CharmBase):
                    def _healthy(self, container):
                        return all(
                            c.status == ops.pebble.CheckStatus.UP
                            for c in container.get_checks().values()
                        )
            """,
        )
        assert findings == []

    def test_yaml_layer_checks_not_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint(
            tmp_charm,
            '''\
                import ops

                LAYER = """
                summary: workload
                services:
                  workload:
                    override: replace
                    command: /bin/workload
                checks:
                  up:
                    override: replace
                    http:
                      url: http://localhost:8080/health
                """

                class C(ops.CharmBase):
                    def _layer(self):
                        return ops.pebble.Layer(LAYER)
            ''',
        )
        assert "FEATURES-002" not in {d.rule_id for d in findings}

    def test_fstring_yaml_layer_checks_not_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint(
            tmp_charm,
            '''\
                import ops

                class C(ops.CharmBase):
                    def _layer(self, port):
                        return ops.pebble.Layer(f"""
                summary: workload
                services:
                  workload:
                    override: replace
                    command: /bin/workload
                checks:
                  up:
                    override: replace
                    http:
                      url: http://localhost:{port}/health
                """)
            ''',
        )
        assert "FEATURES-002" not in {d.rule_id for d in findings}

    def test_empty_checks_mapping_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint(
            tmp_charm,
            """\
                import ops

                class C(ops.CharmBase):
                    def _layer(self):
                        return ops.pebble.Layer({
                            "services": {"workload": {"command": "/bin/workload"}},
                            "checks": {},
                        })
            """,
        )
        assert [d.rule_id for d in findings] == ["FEATURES-002"]

    def test_unrelated_checks_key_does_not_suppress(self, tmp_charm: pathlib.Path):
        """A dict that merely has a ``checks`` key is not a Pebble layer."""
        findings = _lint(
            tmp_charm,
            _NO_CHECKS
            + """\

    def _report(self):
        return [
            {"checks": {"tls": True, "dns": False}},
            {"checks": self._results()},
        ]
""",
        )
        assert [d.rule_id for d in findings] == ["FEATURES-002"]

    def test_observed_check_failed_suppresses(self, tmp_charm: pathlib.Path):
        """A charm handling check failures has checks, wherever they are defined."""
        findings = _lint(
            tmp_charm,
            _NO_CHECKS
            + """\

    def __init__(self, framework):
        super().__init__(framework)
        self.framework.observe(
            self.on.workload_pebble_check_failed, self._on_check_failed
        )

    def _on_check_failed(self, event):
        pass
""",
        )
        assert findings == []

    def test_no_layer_in_charm_source_not_flagged(self, tmp_charm: pathlib.Path):
        """A workload whose plan comes from the rock has checks we cannot see."""
        findings = _lint(
            tmp_charm,
            """\
                import ops

                class C(ops.CharmBase):
                    def _reconcile(self, container):
                        container.replan()
            """,
        )
        assert findings == []

    def test_layer_dict_keyword_form_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint(
            tmp_charm,
            """\
                import ops

                class C(ops.CharmBase):
                    def _layer(self):
                        return ops.pebble.LayerDict(
                            summary="workload",
                            services={
                                "workload": {
                                    "override": "replace",
                                    "command": "/bin/workload",
                                },
                            },
                        )
            """,
        )
        assert [d.rule_id for d in findings] == ["FEATURES-002"]

    def test_checks_keyword_form_not_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint(
            tmp_charm,
            """\
                import ops

                class C(ops.CharmBase):
                    def _layer(self):
                        return ops.pebble.LayerDict(
                            services={
                                "workload": {
                                    "override": "replace",
                                    "command": "/bin/workload",
                                },
                            },
                            checks=self._checks(),
                        )
            """,
        )
        assert findings == []

    def test_vendored_lib_checks_do_not_count(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test", "containers": _CONTAINERS})
        write_charm_source(tmp_charm, textwrap.dedent(_NO_CHECKS))
        lib_dir = tmp_charm / "lib" / "charms" / "someone" / "v0"
        lib_dir.mkdir(parents=True)
        (lib_dir / "helper.py").write_text(
            textwrap.dedent("""\
                LAYER = {
                    "services": {"workload": {"command": "/bin/workload"}},
                    "checks": {"up": {"override": "replace", "tcp": {"port": 8080}}},
                }
            """)
        )
        report = lint(tmp_charm)
        assert "FEATURES-002" in {d.rule_id for d in report}

    def test_own_published_lib_checks_count(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "my-charm", "containers": _CONTAINERS})
        write_charm_source(tmp_charm, textwrap.dedent(_NO_CHECKS))
        lib_dir = tmp_charm / "lib" / "charms" / "my_charm" / "v0"
        lib_dir.mkdir(parents=True)
        (lib_dir / "helper.py").write_text(
            textwrap.dedent("""\
                LAYER = {
                    "services": {"workload": {"command": "/bin/workload"}},
                    "checks": {"up": {"override": "replace", "tcp": {"port": 8080}}},
                }
            """)
        )
        report = lint(tmp_charm)
        findings = [d for d in report if d.rule_id in _PEBBLE_RULES]
        assert [d.rule_id for d in findings] == ["FEATURES-003"]
        assert findings[0].path == "lib/charms/my_charm/v0/helper.py"


class TestUnhandledPebbleCheckFailure:
    """FEATURES-003 — a defined check needs something that responds to failure."""

    def test_checks_without_handler_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint(tmp_charm, _CHECKS)
        assert [d.rule_id for d in findings] == ["FEATURES-003"]
        assert findings[0].severity == Severity.WARNING
        assert findings[0].path == "src/charm.py"
        assert findings[0].line is not None

    def test_no_checks_not_flagged(self, tmp_charm: pathlib.Path):
        findings = _lint(tmp_charm, _NO_CHECKS)
        assert "FEATURES-003" not in {d.rule_id for d in findings}

    def test_observer_suppresses(self, tmp_charm: pathlib.Path):
        findings = _lint(
            tmp_charm,
            _CHECKS
            + """\

    def __init__(self, framework):
        super().__init__(framework)
        self.framework.observe(
            self.on.workload_pebble_check_failed, self._on_check_failed
        )

    def _on_check_failed(self, event):
        self.unit.status = ops.BlockedStatus("workload unhealthy")
""",
        )
        assert findings == []

    def test_subscript_observer_suppresses(self, tmp_charm: pathlib.Path):
        findings = _lint(
            tmp_charm,
            _CHECKS
            + """\

    def __init__(self, framework):
        super().__init__(framework)
        self.framework.observe(
            self.on["workload"].pebble_check_failed, self._on_check_failed
        )

    def _on_check_failed(self, event):
        pass
""",
        )
        assert findings == []

    def test_unresolved_observer_suppresses(self, tmp_charm: pathlib.Path):
        """An observe call the matchers cannot read might be the one wanted."""
        findings = _lint(
            tmp_charm,
            _CHECKS
            + """\

    def __init__(self, framework):
        super().__init__(framework)
        for name in self.meta.containers:
            self.framework.observe(self.on[name].pebble_check_failed, self._failed)

    def _failed(self, event):
        pass
""",
        )
        assert findings == []

    def test_other_observers_do_not_suppress(self, tmp_charm: pathlib.Path):
        findings = _lint(
            tmp_charm,
            _CHECKS
            + """\

    def __init__(self, framework):
        super().__init__(framework)
        self.framework.observe(self.on.config_changed, self._reconcile)
        self.framework.observe(self.on.workload_pebble_ready, self._reconcile)

    def _reconcile(self, event):
        pass
""",
        )
        assert [d.rule_id for d in findings] == ["FEATURES-003"]

    def test_on_check_failure_suppresses(self, tmp_charm: pathlib.Path):
        findings = _lint(
            tmp_charm,
            """\
                import ops

                class C(ops.CharmBase):
                    def _layer(self):
                        return ops.pebble.Layer({
                            "services": {
                                "workload": {
                                    "override": "replace",
                                    "command": "/bin/workload",
                                    "on-check-failure": {"up": "restart"},
                                },
                            },
                            "checks": {
                                "up": {"override": "replace", "tcp": {"port": 8080}},
                            },
                        })
            """,
        )
        assert findings == []

    def test_yaml_on_check_failure_suppresses(self, tmp_charm: pathlib.Path):
        findings = _lint(
            tmp_charm,
            '''\
                import ops

                LAYER = """
                services:
                  workload:
                    override: replace
                    command: /bin/workload
                    on-check-failure:
                      up: restart
                checks:
                  up:
                    override: replace
                    tcp:
                      port: 8080
                """

                class C(ops.CharmBase):
                    def _layer(self):
                        return ops.pebble.Layer(LAYER)
            ''',
        )
        assert findings == []

    def test_check_api_call_suppresses(self, tmp_charm: pathlib.Path):
        """A charm reading its own checks is watching them."""
        findings = _lint(
            tmp_charm,
            _CHECKS
            + """\

    def _healthy(self, container):
        return all(c.status == "up" for c in container.get_checks().values())
""",
        )
        assert findings == []

    def test_checks_handed_to_a_helper_suppresses(self, tmp_charm: pathlib.Path):
        """A keyword naming Pebble checks hands them to something watching them."""
        findings = _lint(
            tmp_charm,
            _CHECKS
            + """\

    def _status(self, event):
        StatusManager(
            charm=self, block_if_pebble_checks_failing={"workload": ["up"]}
        ).collect_status(event)
""",
        )
        assert findings == []

    def test_checks_without_layer_markers_flagged(self, tmp_charm: pathlib.Path):
        """Checks added on their own are still checks."""
        findings = _lint(
            tmp_charm,
            """\
                import ops

                class C(ops.CharmBase):
                    def _add(self, container):
                        container.add_layer(
                            "checks",
                            {"checks": {"up": {"override": "replace", "level": "ready"}}},
                            combine=True,
                        )
            """,
        )
        assert [d.rule_id for d in findings] == ["FEATURES-003"]

    def test_vendored_lib_observer_does_not_suppress(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test", "containers": _CONTAINERS})
        write_charm_source(tmp_charm, textwrap.dedent(_CHECKS))
        lib_dir = tmp_charm / "lib" / "charms" / "someone" / "v0"
        lib_dir.mkdir(parents=True)
        (lib_dir / "helper.py").write_text(
            textwrap.dedent("""\
                class Helper:
                    def __init__(self, charm):
                        charm.framework.observe(
                            charm.on.workload_pebble_check_failed, self._failed
                        )

                    def _failed(self, event):
                        pass
            """)
        )
        report = lint(tmp_charm)
        assert "FEATURES-003" in {d.rule_id for d in report}

    def test_checks_in_tests_do_not_count(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test", "containers": _CONTAINERS})
        write_charm_source(tmp_charm, textwrap.dedent(_NO_CHECKS))
        (tmp_charm / "tests" / "unit").mkdir(parents=True)
        (tmp_charm / "tests" / "unit" / "test_charm.py").write_text(
            textwrap.dedent("""\
                LAYER = {
                    "services": {"workload": {"command": "/bin/workload"}},
                    "checks": {"up": {"override": "replace", "tcp": {"port": 8080}}},
                }
            """)
        )
        report = lint(tmp_charm)
        ids = {d.rule_id for d in report}
        assert "FEATURES-002" in ids
        assert "FEATURES-003" not in ids


RULE_ID = "FEATURES-004"


def _hits(charm_dir: pathlib.Path):
    return [d for d in list(lint(charm_dir)) if d.rule_id == RULE_ID]


class TestNoAssumesJujuVersion:
    """Tests for FEATURES-004 — no `assumes:` Juju version constraint."""

    def test_no_assumes_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        hits = _hits(tmp_charm)
        assert len(hits) == 1
        assert hits[0].severity == Severity.INFO
        assert hits[0].path == "charmcraft.yaml"
        # There is no `assumes` key to anchor to.
        assert hits[0].line is None

    def test_empty_assumes_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x", "assumes": []})
        assert len(_hits(tmp_charm)) == 1

    def test_assumes_without_juju_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x", "assumes": ["k8s-api"]})
        hits = _hits(tmp_charm)
        assert len(hits) == 1
        # The `assumes` block exists, so the finding anchors to its key.
        assert hits[0].line is not None

    def test_string_form_suppresses(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x", "assumes": ["juju >= 3.6"]})
        assert not _hits(tmp_charm)

    def test_mapping_form_suppresses(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "x", "assumes": [{"juju": ">= 3.6"}, "k8s-api"]},
        )
        assert not _hits(tmp_charm)

    def test_upper_bound_only_suppresses(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x", "assumes": ["juju < 4"]})
        assert not _hits(tmp_charm)

    def test_any_of_group_suppresses(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "x", "assumes": [{"any-of": ["juju >= 2.9.44", "juju >= 3.1.6"]}]},
        )
        assert not _hits(tmp_charm)

    def test_nested_all_of_group_suppresses(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "x",
                "assumes": [
                    "k8s-api",
                    {"any-of": [{"all-of": ["juju >= 3.1", "k8s-api"]}, "juju >= 2.9"]},
                ],
            },
        )
        assert not _hits(tmp_charm)

    def test_group_without_juju_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "x", "assumes": [{"any-of": ["k8s-api", "shared-fs"]}]},
        )
        assert len(_hits(tmp_charm)) == 1

    def test_bare_juju_without_version_flagged(self, tmp_charm: pathlib.Path):
        # `juju` on its own is not a version constraint.
        write_charmcraft_yaml(tmp_charm, {"name": "x", "assumes": ["juju"]})
        assert len(_hits(tmp_charm)) == 1

    def test_bare_juju_mapping_without_version_flagged(self, tmp_charm: pathlib.Path):
        # `- juju:` parses to `{"juju": None}` — the mapping-form
        # equivalent of a bare `juju`, and just as much not a constraint.
        write_charmcraft_yaml(tmp_charm, {"name": "x", "assumes": [{"juju": None}]})
        assert len(_hits(tmp_charm)) == 1

    def test_juju_prefixed_feature_does_not_suppress(self, tmp_charm: pathlib.Path):
        # A hypothetical feature whose name merely starts with "juju".
        write_charmcraft_yaml(tmp_charm, {"name": "x", "assumes": ["juju-secrets"]})
        assert len(_hits(tmp_charm)) == 1

    def test_split_metadata_charm_not_flagged(self, tmp_charm: pathlib.Path):
        # `name` still lives in metadata.yaml: a pre-unification layout,
        # which the rule leaves alone.
        (tmp_charm / "charmcraft.yaml").write_text("type: charm\n")
        (tmp_charm / "metadata.yaml").write_text("name: x\n")
        assert not _hits(tmp_charm)

    def test_metadata_yaml_only_charm_not_flagged(self, tmp_charm: pathlib.Path):
        (tmp_charm / "metadata.yaml").write_text("name: x\nsummary: s\n")
        assert not _hits(tmp_charm)

    def test_anchors_at_the_assumes_key(self, tmp_charm: pathlib.Path):
        (tmp_charm / "charmcraft.yaml").write_text("name: x\nassumes:\n  - k8s-api\n")
        hits = _hits(tmp_charm)
        assert len(hits) == 1
        assert hits[0].path == "charmcraft.yaml"
        assert hits[0].line == 2

    def test_bundle_not_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"type": "bundle", "name": "x"})
        assert not _hits(tmp_charm)

    def test_malformed_assumes_flagged_not_crashed(self, tmp_charm: pathlib.Path):
        # A mapping where a list belongs: the charm declares nothing usable.
        write_charmcraft_yaml(tmp_charm, {"name": "x", "assumes": {"juju": ">= 3.6"}})
        assert len(_hits(tmp_charm)) == 1

    def test_non_scalar_assumes_entry_flagged(self, tmp_charm: pathlib.Path):
        # An entry that is neither a string nor a mapping can't name a
        # feature, so it neither satisfies nor crashes the rule.
        write_charmcraft_yaml(tmp_charm, {"name": "x", "assumes": [["juju >= 3.6"]]})
        assert len(_hits(tmp_charm)) == 1

    def test_charm_without_metadata_not_flagged(self, tmp_charm: pathlib.Path):
        # Nothing to read: METADATA-001 is the finding here, not this rule.
        assert not _hits(tmp_charm)

    def test_noqa_on_assumes_line_suppresses(self, tmp_charm: pathlib.Path):
        (tmp_charm / "charmcraft.yaml").write_text(
            "name: x\nassumes:  # noqa: FEATURES-004\n  - k8s-api\n"
        )
        assert not _hits(tmp_charm)
