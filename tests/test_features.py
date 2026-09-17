"""Tests for FEATURES rules."""

import pathlib

from charmlint._linter import lint
from charmlint._models import Severity
from tests.conftest import write_charmcraft_yaml

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
