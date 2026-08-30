"""Tests for the supply chain rules."""

import pathlib

from charmlint._linter import lint
from charmlint._models import Severity
from tests.conftest import write_charmcraft_yaml

RULE = "SUPPLYCHAIN-001"


def _hits(charm_dir: pathlib.Path) -> list:
    return [d for d in lint(charm_dir) if d.rule_id == RULE]


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
        diags = _hits(tmp_charm)
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
        assert not _hits(tmp_charm)

    def test_empty_upstream_source_still_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "resources": {"workload-image": {"type": "oci-image", "upstream-source": ""}},
            },
        )
        assert len(_hits(tmp_charm)) == 1

    def test_file_resource_not_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "resources": {"snap": {"type": "file", "filename": "workload.snap"}},
            },
        )
        assert not _hits(tmp_charm)

    def test_no_resources_at_all(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        assert not _hits(tmp_charm)

    def test_malformed_resources_ignored(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test", "resources": ["workload-image"]})
        assert not _hits(tmp_charm)

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
        assert {d.message.split("'")[1] for d in _hits(tmp_charm)} == {"a-image", "b-image"}

    def test_diagnostic_anchors_on_the_resource(self, tmp_charm: pathlib.Path):
        (tmp_charm / "charmcraft.yaml").write_text(
            "name: test\nresources:\n  workload-image:\n    type: oci-image\n"
        )
        diags = _hits(tmp_charm)
        assert len(diags) == 1
        assert diags[0].line == 3

    def test_noqa_on_the_resource_line_suppresses(self, tmp_charm: pathlib.Path):
        (tmp_charm / "charmcraft.yaml").write_text(
            "name: test\n"
            "resources:\n"
            "  workload-image:  # noqa: SUPPLYCHAIN-001\n"
            "    type: oci-image\n"
        )
        assert not _hits(tmp_charm)

    def test_file_level_noqa_suppresses(self, tmp_charm: pathlib.Path):
        (tmp_charm / "charmcraft.yaml").write_text(
            "# charmlint: noqa: SUPPLYCHAIN\n"
            "name: test\n"
            "resources:\n"
            "  workload-image:\n"
            "    type: oci-image\n"
        )
        assert not _hits(tmp_charm)

    def test_noqa_on_one_resource_leaves_the_other(self, tmp_charm: pathlib.Path):
        (tmp_charm / "charmcraft.yaml").write_text(
            "name: test\n"
            "resources:\n"
            "  a-image:  # noqa: SUPPLYCHAIN-001\n"
            "    type: oci-image\n"
            "  b-image:\n"
            "    type: oci-image\n"
        )
        diags = _hits(tmp_charm)
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
        assert not _hits(tmp_charm)

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
        assert not _hits(tmp_charm)

    def test_rock_two_directories_down_not_flagged(self, tmp_charm: pathlib.Path):
        """The multi-rock `foo_rocks/<component>/rockcraft.yaml` layout."""
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "test", "resources": {"datahub-gms": {"type": "oci-image"}}},
        )
        rock = tmp_charm / "datahub_rocks" / "gms"
        rock.mkdir(parents=True)
        (rock / "rockcraft.yaml").write_text("name: datahub-gms\nbase: ubuntu@24.04\n")
        assert not _hits(tmp_charm)

    def test_image_built_from_an_in_repo_dockerfile_not_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "test", "resources": {"workload-image": {"type": "oci-image"}}},
        )
        image_dir = tmp_charm / "workload"
        image_dir.mkdir()
        (image_dir / "Dockerfile").write_text("FROM ubuntu:24.04\n")
        assert not _hits(tmp_charm)

    def test_unrelated_rock_does_not_exempt_the_resource(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "test", "resources": {"redis-image": {"type": "oci-image"}}},
        )
        rock = tmp_charm / "workload_rock"
        rock.mkdir()
        (rock / "rockcraft.yaml").write_text("name: workload\nbase: ubuntu@24.04\n")
        assert len(_hits(tmp_charm)) == 1

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
        diags = _hits(tmp_charm)
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
        assert len(_hits(tmp_charm)) == 1

    def test_resources_in_legacy_metadata_yaml(self, tmp_charm: pathlib.Path):
        (tmp_charm / "metadata.yaml").write_text(
            "name: test\nresources:\n  workload-image:\n    type: oci-image\n"
        )
        diags = _hits(tmp_charm)
        assert len(diags) == 1
        assert diags[0].path == "metadata.yaml"
        assert diags[0].line == 3

    def test_resources_in_the_metadata_half_of_a_split_charm(self, tmp_charm: pathlib.Path):
        """The diagnostic follows `resources` into whichever file holds it."""
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        (tmp_charm / "metadata.yaml").write_text(
            "summary: s\nresources:\n  workload-image:\n    type: oci-image\n"
        )
        diags = _hits(tmp_charm)
        assert len(diags) == 1
        assert diags[0].path == "metadata.yaml"
        assert diags[0].line == 3
