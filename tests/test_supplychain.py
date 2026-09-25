"""Tests for SUPPLYCHAIN rules."""

import pathlib

from charmlint._linter import lint
from charmlint._models import Severity
from charmlint._rules import supplychain as _supplychain
from tests.conftest import write_charmcraft_yaml

_OCI_RULE = "SUPPLYCHAIN-001"


def _oci_hits(charm_dir: pathlib.Path) -> list:
    return [d for d in lint(charm_dir) if d.rule_id == _OCI_RULE]


class TestOciImageMissingUpstreamSource:
    """Tests for SUPPLYCHAIN-001 — oci-image without upstream-source."""

    def test_oci_image_without_upstream_source(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "resources": {
                    "workload-image": {"type": "oci-image", "description": "the workload"},
                },
            },
        )
        diags = _oci_hits(tmp_charm)
        assert len(diags) == 1
        assert diags[0].severity == Severity.INFO
        assert "workload-image" in diags[0].message
        assert diags[0].path == "charmcraft.yaml"

    def test_oci_image_with_upstream_source(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "resources": {
                    "workload-image": {
                        "type": "oci-image",
                        "upstream-source": "ghcr.io/canonical/foo:1.2.3",
                    },
                },
            },
        )
        assert not _oci_hits(tmp_charm)

    def test_empty_upstream_source_still_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "resources": {"workload-image": {"type": "oci-image", "upstream-source": ""}},
            },
        )
        assert len(_oci_hits(tmp_charm)) == 1

    def test_file_resource_not_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "resources": {"snap": {"type": "file", "filename": "workload.snap"}},
            },
        )
        assert not _oci_hits(tmp_charm)

    def test_no_resources_at_all(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        assert not _oci_hits(tmp_charm)

    def test_malformed_resources_ignored(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test", "resources": ["workload-image"]})
        assert not _oci_hits(tmp_charm)

    def test_each_offending_resource_flagged_once(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "resources": {
                    "a-image": {"type": "oci-image"},
                    "b-image": {"type": "oci-image"},
                    "c-image": {"type": "oci-image", "upstream-source": "example.com/c:1"},
                },
            },
        )
        assert {d.message.split("'")[1] for d in _oci_hits(tmp_charm)} == {"a-image", "b-image"}

    def test_diagnostic_anchors_on_the_resource(self, tmp_charm: pathlib.Path):
        (tmp_charm / "charmcraft.yaml").write_text(
            "name: test\nresources:\n  workload-image:\n    type: oci-image\n"
        )
        diags = _oci_hits(tmp_charm)
        assert len(diags) == 1
        assert diags[0].line == 3

    def test_noqa_on_the_resource_line_suppresses(self, tmp_charm: pathlib.Path):
        (tmp_charm / "charmcraft.yaml").write_text(
            "name: test\n"
            "resources:\n"
            "  workload-image:  # noqa: SUPPLYCHAIN-001\n"
            "    type: oci-image\n"
        )
        assert not _oci_hits(tmp_charm)

    def test_file_level_noqa_suppresses(self, tmp_charm: pathlib.Path):
        (tmp_charm / "charmcraft.yaml").write_text(
            "# charmlint: file-ignore[SUPPLYCHAIN]\n"
            "name: test\n"
            "resources:\n"
            "  workload-image:\n"
            "    type: oci-image\n"
        )
        assert not _oci_hits(tmp_charm)

    def test_noqa_on_one_resource_leaves_the_other(self, tmp_charm: pathlib.Path):
        (tmp_charm / "charmcraft.yaml").write_text(
            "name: test\n"
            "resources:\n"
            "  a-image:  # noqa: SUPPLYCHAIN-001\n"
            "    type: oci-image\n"
            "  b-image:\n"
            "    type: oci-image\n"
        )
        diags = _oci_hits(tmp_charm)
        assert len(diags) == 1
        assert "b-image" in diags[0].message

    def test_image_built_from_an_in_repo_rock_not_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "test", "resources": {"workload-image": {"type": "oci-image"}}},
        )
        rock = tmp_charm / "workload_rock"
        rock.mkdir()
        (rock / "rockcraft.yaml").write_text("name: workload\nbase: ubuntu@24.04\n")
        assert not _oci_hits(tmp_charm)

    def test_rock_in_a_generically_named_directory_matched_by_its_name(
        self, tmp_charm: pathlib.Path
    ):
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "test", "resources": {"hive-metastore-image": {"type": "oci-image"}}},
        )
        rock = tmp_charm / "rock"
        rock.mkdir()
        (rock / "rockcraft.yaml").write_text("name: hive_metastore\nbase: ubuntu@24.04\n")
        assert not _oci_hits(tmp_charm)

    def test_rock_two_directories_down_not_flagged(self, tmp_charm: pathlib.Path):
        """The multi-rock `foo_rocks/<component>/rockcraft.yaml` layout."""
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "test", "resources": {"datahub-gms": {"type": "oci-image"}}},
        )
        rock = tmp_charm / "datahub_rocks" / "gms"
        rock.mkdir(parents=True)
        (rock / "rockcraft.yaml").write_text("name: datahub-gms\nbase: ubuntu@24.04\n")
        assert not _oci_hits(tmp_charm)

    def test_image_built_from_an_in_repo_dockerfile_not_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "test", "resources": {"workload-image": {"type": "oci-image"}}},
        )
        image_dir = tmp_charm / "workload"
        image_dir.mkdir()
        (image_dir / "Dockerfile").write_text("FROM ubuntu:24.04\n")
        assert not _oci_hits(tmp_charm)

    def test_rock_beside_the_charm_in_a_monorepo_not_flagged(self, tmp_path: pathlib.Path):
        """The `app/charm/` beside `app/rockcraft.yaml` layout."""
        (tmp_path / ".git").mkdir()
        app = tmp_path / "app"
        charm_dir = app / "charm"
        charm_dir.mkdir(parents=True)
        write_charmcraft_yaml(
            charm_dir,
            {"name": "test", "resources": {"sync-bot": {"type": "oci-image"}}},
        )
        (app / "rockcraft.yaml").write_text("name: sync-bot\nbase: ubuntu@24.04\n")
        assert not _oci_hits(charm_dir)

    def test_dockerfile_at_the_repository_root_not_flagged(self, tmp_path: pathlib.Path):
        repo = tmp_path / "candid"
        (repo / ".git").mkdir(parents=True)
        charm_dir = repo / "charms" / "candid-k8s"
        charm_dir.mkdir(parents=True)
        write_charmcraft_yaml(
            charm_dir,
            {"name": "test", "resources": {"candid-image": {"type": "oci-image"}}},
        )
        (repo / "Dockerfile").write_text("FROM ubuntu:24.04\n")
        assert not _oci_hits(charm_dir)

    def test_rock_above_a_charm_outside_git_not_considered(self, tmp_path: pathlib.Path):
        """Without a repository root, the search stays inside the charm."""
        charm_dir = tmp_path / "charm"
        charm_dir.mkdir()
        write_charmcraft_yaml(
            charm_dir,
            {"name": "test", "resources": {"sync-bot": {"type": "oci-image"}}},
        )
        (tmp_path / "rockcraft.yaml").write_text("name: sync-bot\nbase: ubuntu@24.04\n")
        assert len(_oci_hits(charm_dir)) == 1

    def test_unrelated_rock_does_not_exempt_the_resource(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "test", "resources": {"redis-image": {"type": "oci-image"}}},
        )
        rock = tmp_charm / "workload_rock"
        rock.mkdir()
        (rock / "rockcraft.yaml").write_text("name: workload\nbase: ubuntu@24.04\n")
        assert len(_oci_hits(tmp_charm)) == 1

    def test_nameless_rock_falls_back_to_its_directory(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "resources": {
                    "workload-image": {"type": "oci-image"},
                    "redis-image": {"type": "oci-image"},
                },
            },
        )
        rock = tmp_charm / "workload-rock"
        rock.mkdir()
        (rock / "rockcraft.yaml").write_text("base: ubuntu@24.04\n")
        diags = _oci_hits(tmp_charm)
        assert len(diags) == 1
        assert "redis-image" in diags[0].message

    def test_unparseable_rock_does_not_exempt_the_resource(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "test", "resources": {"redis-image": {"type": "oci-image"}}},
        )
        rock = tmp_charm / "rock"
        rock.mkdir()
        (rock / "rockcraft.yaml").write_text("name: [\n")
        assert len(_oci_hits(tmp_charm)) == 1

    def test_resources_in_legacy_metadata_yaml(self, tmp_charm: pathlib.Path):
        (tmp_charm / "metadata.yaml").write_text(
            "name: test\nresources:\n  workload-image:\n    type: oci-image\n"
        )
        diags = _oci_hits(tmp_charm)
        assert len(diags) == 1
        assert diags[0].path == "metadata.yaml"
        assert diags[0].line == 3

    def test_resources_in_the_metadata_half_of_a_split_charm(self, tmp_charm: pathlib.Path):
        """The diagnostic follows `resources` into whichever file holds it."""
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        (tmp_charm / "metadata.yaml").write_text(
            "summary: s\nresources:\n  workload-image:\n    type: oci-image\n"
        )
        diags = _oci_hits(tmp_charm)
        assert len(diags) == 1
        assert diags[0].path == "metadata.yaml"
        assert diags[0].line == 3


class TestOpsPinningRules:
    """Tests for the ops dependency pinning rules."""

    def test_supplychain005_bare_ops_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "requirements.txt").write_text("ops\n")
        report = lint(tmp_charm)
        hits = [d for d in report if d.rule_id == "SUPPLYCHAIN-005"]
        assert len(hits) == 1
        assert hits[0].severity == Severity.WARNING
        assert not [d for d in report if d.rule_id == "SUPPLYCHAIN-006"]

    def test_supplychain005_bare_ops_extras_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "requirements.txt").write_text("ops[tracing]\n")
        report = lint(tmp_charm)
        assert [d for d in report if d.rule_id == "SUPPLYCHAIN-005"]

    def test_supplychain005_bare_ops_in_pyproject_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "pyproject.toml").write_text(
            '[project]\nname = "x"\ndependencies = [\n  "ops",\n]\n'
        )
        report = lint(tmp_charm)
        assert [d for d in report if d.rule_id == "SUPPLYCHAIN-005"]

    def test_range_pin_passes(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "requirements.txt").write_text("ops>=2.23,<4\n")
        report = lint(tmp_charm)
        assert not [d for d in report if d.rule_id in {"SUPPLYCHAIN-005", "SUPPLYCHAIN-006"}]

    def test_editing_requirements_between_runs_is_seen(self, tmp_charm: pathlib.Path):
        # Nothing about the charm may outlive a lint() call: an editor
        # integration or a watch mode lints the same path repeatedly.
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        requirements = tmp_charm / "requirements.txt"
        requirements.write_text("ops==3.7.1\n")
        assert [d for d in lint(tmp_charm) if d.rule_id == "SUPPLYCHAIN-006"]
        requirements.write_text("ops>=2.23,<4\n")
        assert not [d for d in lint(tmp_charm) if d.rule_id == "SUPPLYCHAIN-006"]

    def test_supplychain006_exact_pin_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "requirements.txt").write_text("ops==3.7.1\n")
        report = lint(tmp_charm)
        hits = [d for d in report if d.rule_id == "SUPPLYCHAIN-006"]
        assert len(hits) == 1
        assert hits[0].severity == Severity.INFO
        assert hits[0].line == 1
        assert not [d for d in report if d.rule_id == "SUPPLYCHAIN-005"]

    def test_requirements_line_number_is_reported(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "requirements.txt").write_text("# a comment\nrequests>=2.0\n\nops==3.7.1\n")
        report = lint(tmp_charm)
        hits = [d for d in report if d.rule_id == "SUPPLYCHAIN-006"]
        assert len(hits) == 1
        assert hits[0].line == 4

    def test_supplychain006_exact_pin_in_pyproject_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "pyproject.toml").write_text('[project]\ndependencies = ["ops==3.7.1"]\n')
        report = lint(tmp_charm)
        assert [d for d in report if d.rule_id == "SUPPLYCHAIN-006"]

    def test_no_ops_dependency_not_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "requirements.txt").write_text("requests>=2.0\n")
        report = lint(tmp_charm)
        assert not [d for d in report if d.rule_id in {"SUPPLYCHAIN-005", "SUPPLYCHAIN-006"}]

    def test_pyproject_ops_in_keywords_not_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "pyproject.toml").write_text(
            "[project]\n"
            'name = "ops"\n'
            'keywords = ["ops", "charm"]\n'
            'dependencies = ["ops>=2.23,<4"]\n'
        )
        report = lint(tmp_charm)
        assert not [d for d in report if d.rule_id in {"SUPPLYCHAIN-005", "SUPPLYCHAIN-006"}]

    def test_pyproject_optional_dependencies_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "pyproject.toml").write_text(
            "[project]\n"
            'name = "x"\n'
            "dependencies = []\n"
            "\n"
            "[project.optional-dependencies]\n"
            'tracing = ["ops==3.7.1"]\n'
        )
        report = lint(tmp_charm)
        assert [d for d in report if d.rule_id == "SUPPLYCHAIN-006"]

    def test_pyproject_dependency_groups_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "pyproject.toml").write_text(
            '[project]\nname = "x"\n\n[dependency-groups]\ndev = ["ops"]\n'
        )
        report = lint(tmp_charm)
        assert [d for d in report if d.rule_id == "SUPPLYCHAIN-005"]

    def test_poetry_caret_pin_not_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "pyproject.toml").write_text(
            "[tool.poetry]\n"
            'name = "x"\n'
            "\n"
            "[tool.poetry.dependencies]\n"
            'python = "^3.10"\n'
            'ops = "^2.23"\n'
        )
        report = lint(tmp_charm)
        assert not [d for d in report if d.rule_id in {"SUPPLYCHAIN-005", "SUPPLYCHAIN-006"}]

    def test_poetry_star_unpinned_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "pyproject.toml").write_text('[tool.poetry.dependencies]\nops = "*"\n')
        report = lint(tmp_charm)
        assert [d for d in report if d.rule_id == "SUPPLYCHAIN-005"]

    def test_poetry_exact_pin_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "pyproject.toml").write_text('[tool.poetry.dependencies]\nops = "==3.7.1"\n')
        report = lint(tmp_charm)
        assert [d for d in report if d.rule_id == "SUPPLYCHAIN-006"]

    def test_poetry_table_version_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "pyproject.toml").write_text(
            '[tool.poetry.dependencies]\nops = { version = "==3.7.1", extras = ["tracing"] }\n'
        )
        report = lint(tmp_charm)
        assert [d for d in report if d.rule_id == "SUPPLYCHAIN-006"]

    def test_poetry_group_dependencies_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "pyproject.toml").write_text(
            '[tool.poetry.group.dev.dependencies]\nops = "==3.7.1"\n'
        )
        report = lint(tmp_charm)
        assert [d for d in report if d.rule_id == "SUPPLYCHAIN-006"]

    def test_malformed_pyproject_reported_as_fatal(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "pyproject.toml").write_text("this is [not valid toml\n")
        (tmp_charm / "requirements.txt").write_text("ops==3.7.1\n")
        report = lint(tmp_charm)
        # A broken pyproject.toml is reported, not silently skipped in
        # favour of requirements.txt: the charm's real dependency
        # declaration could not be read, so a clean JUJU report would be
        # a lie.
        fatal = [d for d in report if d.rule_id == "FATAL"]
        assert len(fatal) == 1
        assert "pyproject.toml" in fatal[0].message
        assert not [d for d in report if d.rule_id in {"SUPPLYCHAIN-005", "SUPPLYCHAIN-006"}]

    def test_uv_plugin_ignores_requirements_txt(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x", "parts": {"my-charm": {"plugin": "uv"}}})
        (tmp_charm / "requirements.txt").write_text("ops==3.7.1\n")
        report = lint(tmp_charm)
        assert not [d for d in report if d.rule_id in {"SUPPLYCHAIN-005", "SUPPLYCHAIN-006"}]

    def test_poetry_plugin_ignores_requirements_txt(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm, {"name": "x", "parts": {"my-charm": {"plugin": "poetry"}}}
        )
        (tmp_charm / "requirements.txt").write_text("ops\n")
        report = lint(tmp_charm)
        assert not [d for d in report if d.rule_id in {"SUPPLYCHAIN-005", "SUPPLYCHAIN-006"}]

    def test_uv_plugin_still_checks_pyproject(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x", "parts": {"my-charm": {"plugin": "uv"}}})
        (tmp_charm / "pyproject.toml").write_text(
            '[project]\nname = "x"\ndependencies = [\n  "ops==3.7.1",\n]\n'
        )
        report = lint(tmp_charm)
        assert [d for d in report if d.rule_id == "SUPPLYCHAIN-006"]

    def test_charm_plugin_still_checks_requirements_txt(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x", "parts": {"my-charm": {"plugin": "charm"}}})
        (tmp_charm / "requirements.txt").write_text("ops==3.7.1\n")
        report = lint(tmp_charm)
        assert [d for d in report if d.rule_id == "SUPPLYCHAIN-006"]

    def test_non_dependency_plugin_checks_requirements_txt(self, tmp_charm: pathlib.Path):
        # nil and dump put files in the payload without resolving
        # anything, so they say nothing about where ops is declared and
        # the default requirements.txt still applies.
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "x", "parts": {"files": {"plugin": "dump"}, "hooks": {"plugin": "nil"}}},
        )
        (tmp_charm / "requirements.txt").write_text("ops==3.7.1\n")
        report = lint(tmp_charm)
        assert [d for d in report if d.rule_id == "SUPPLYCHAIN-006"]

    def test_python_plugin_reads_declared_requirements_files(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "x",
                "parts": {
                    "my-charm": {
                        "plugin": "python",
                        "python-requirements": ["deps/runtime.txt"],
                    }
                },
            },
        )
        (tmp_charm / "deps").mkdir()
        (tmp_charm / "deps" / "runtime.txt").write_text("ops==3.7.1\n")
        # A requirements.txt that the plugin does not read is not the
        # charm's declaration, so it must not be what we report on.
        (tmp_charm / "requirements.txt").write_text("ops>=2.23,<4\n")
        report = lint(tmp_charm)
        pinned = [d for d in report if d.rule_id == "SUPPLYCHAIN-006"]
        assert len(pinned) == 1
        assert pinned[0].path == "deps/runtime.txt"

    def test_python_plugin_without_declaration_falls_back(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm, {"name": "x", "parts": {"my-charm": {"plugin": "python"}}}
        )
        (tmp_charm / "requirements.txt").write_text("ops==3.7.1\n")
        report = lint(tmp_charm)
        assert [d for d in report if d.rule_id == "SUPPLYCHAIN-006"]


class TestOpsDependencyParsing:
    """The parsed ops dependency, which every JUJU pinning rule works from."""

    def test_pep508_specifier_extras_and_section(self):
        dep = _supplychain._parse_pep508(
            "ops[tracing,testing]>=2.23,<4", "pyproject.toml", "project.dependencies"
        )
        assert dep is not None
        assert dep.specifier == ">=2.23,<4"
        assert dep.extras == ("tracing", "testing")
        assert dep.section == "project.dependencies"
        assert dep.line is None
        assert not dep.is_unpinned
        assert not dep.is_exact

    def test_pep508_environment_marker_dropped(self):
        dep = _supplychain._parse_pep508(
            'ops>=2.23; python_version < "3.12"', "requirements.txt", "requirements.txt"
        )
        assert dep is not None
        assert dep.specifier == ">=2.23"

    def test_pep508_non_ops_ignored(self):
        assert (
            _supplychain._parse_pep508(
                "operator-libs-linux", "requirements.txt", "requirements.txt"
            )
            is None
        )

    def test_pep508_bare_is_unpinned(self):
        dep = _supplychain._parse_pep508("ops", "requirements.txt", "requirements.txt")
        assert dep is not None
        assert dep.specifier == ""
        assert dep.is_unpinned

    def test_poetry_table_keeps_version_and_extras(self):
        dep = _supplychain._parse_poetry(
            {"version": "==3.7.1", "extras": ["tracing"]},
            "pyproject.toml",
            "tool.poetry.dependencies",
        )
        assert dep.specifier == "==3.7.1"
        assert dep.extras == ("tracing",)
        assert dep.is_exact

    def test_poetry_wildcard_is_unpinned(self):
        dep = _supplychain._parse_poetry("*", "pyproject.toml", "tool.poetry.dependencies")
        assert dep.is_unpinned

    def test_section_recorded_for_optional_dependencies(self):
        dep = _supplychain._find_ops_in_pyproject(
            {"project": {"optional-dependencies": {"dev": ["ops==3.7.1"]}}}
        )
        assert dep is not None
        assert dep.section == "project.optional-dependencies.dev"

    def test_section_recorded_for_dependency_groups(self):
        dep = _supplychain._find_ops_in_pyproject({"dependency-groups": {"test": ["ops"]}})
        assert dep is not None
        assert dep.section == "dependency-groups.test"

    def test_section_recorded_for_poetry_group(self):
        dep = _supplychain._find_ops_in_pyproject(
            {"tool": {"poetry": {"group": {"dev": {"dependencies": {"ops": "==3.7.1"}}}}}}
        )
        assert dep is not None
        assert dep.section == "tool.poetry.group.dev.dependencies"

    def test_testing_extra_is_skipped(self):
        """`ops[testing]` is the test harness, not the charm's runtime dependency."""
        dep = _supplychain._find_ops_in_pyproject(
            {"project": {"optional-dependencies": {"dev": ["ops[testing]"]}}}
        )
        assert dep is None

    def test_runtime_wins_over_a_testing_extra(self):
        """A test-group declaration is stepped over, not returned in place of the runtime one."""
        dep = _supplychain._find_ops_in_pyproject(
            {
                "project": {"dependencies": ["ops>=3,<4"]},
                "dependency-groups": {"unit": ["ops[testing]"]},
            }
        )
        assert dep is not None
        assert dep.section == "project.dependencies"
        assert dep.specifier == ">=3,<4"

    def test_testing_extra_skipped_in_dependency_groups(self):
        dep = _supplychain._find_ops_in_pyproject(
            {"dependency-groups": {"unit": ["ops[testing]"]}}
        )
        assert dep is None

    def test_testing_extra_skipped_for_poetry(self):
        dep = _supplychain._find_ops_in_pyproject(
            {
                "tool": {
                    "poetry": {
                        "dependencies": {"ops": {"version": "*", "extras": ["testing"]}},
                        "group": {
                            "unit": {
                                "dependencies": {"ops": {"version": "*", "extras": ["testing"]}}
                            }
                        },
                    }
                }
            }
        )
        assert dep is None

    def test_testing_extra_skipped_in_requirements(self, tmp_charm: pathlib.Path):
        path = tmp_charm / "requirements.txt"
        path.write_text("ops[testing]\n")
        assert _supplychain._find_ops_in_requirements(path) is None

    def test_requirements_line_recorded(self, tmp_charm: pathlib.Path):
        path = tmp_charm / "requirements.txt"
        path.write_text("# a comment\n-r other.txt\n\nops==3.7.1\n")
        dep = _supplychain._find_ops_in_requirements(path)
        assert dep is not None
        assert dep.line == 4
        assert dep.section == "requirements.txt"

    def test_where_names_a_pyproject_section(self):
        dep = _supplychain._parse_pep508("ops", "pyproject.toml", "dependency-groups.test")
        assert dep is not None
        assert dep.where == " in `dependency-groups.test`"

    def test_where_empty_for_requirements(self):
        dep = _supplychain._parse_pep508("ops", "requirements.txt", "requirements.txt")
        assert dep is not None
        assert dep.where == ""


class TestSectionInMessages:
    """The section a dependency was declared in reaching the diagnostic."""

    def test_pyproject_message_names_the_section(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "pyproject.toml").write_text('[project]\ndependencies = ["ops==3.7.1"]\n')
        report = lint(tmp_charm)
        hits = [d for d in report if d.rule_id == "SUPPLYCHAIN-006"]
        assert len(hits) == 1
        assert "in `project.dependencies`" in hits[0].message

    def test_requirements_message_does_not_repeat_the_file(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        (tmp_charm / "requirements.txt").write_text("ops\n")
        report = lint(tmp_charm)
        hits = [d for d in report if d.rule_id == "SUPPLYCHAIN-005"]
        assert len(hits) == 1
        assert "requirements.txt" not in hits[0].message
        assert hits[0].path == "requirements.txt"
