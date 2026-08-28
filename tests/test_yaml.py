"""Tests for charmlint._yaml and the Yaml value model."""

import pathlib

import pytest

from charmlint import _yaml
from charmlint._models import Yaml


def _write(tmp_path: pathlib.Path, name: str, content: str) -> pathlib.Path:
    path = tmp_path / name
    path.write_text(content)
    return path


class TestLoad:
    """Loading a file into a provenance-carrying tree."""

    def test_absent_file(self, tmp_path: pathlib.Path):
        node = _yaml.load(tmp_path / "charmcraft.yaml")
        assert not node.present
        assert node.value is None
        assert node.source == "charmcraft.yaml"

    def test_empty_file(self, tmp_path: pathlib.Path):
        # An empty file composes to nothing, which is the same "no metadata
        # here" state as a file that isn't there at all.
        node = _yaml.load(_write(tmp_path, "charmcraft.yaml", ""))
        assert not node.present

    def test_values_and_source(self, tmp_path: pathlib.Path):
        node = _yaml.load(_write(tmp_path, "charmcraft.yaml", "name: test\nsummary: hi\n"))
        assert node.value == {"name": "test", "summary": "hi"}
        assert node["name"].value == "test"
        assert node["name"].source == "charmcraft.yaml"

    def test_line_is_the_key_line(self, tmp_path: pathlib.Path):
        # A ``noqa`` comment sits on the key's own line, so that is the line
        # a value is attributed to — not the line its nested value starts on.
        node = _yaml.load(
            _write(
                tmp_path,
                "charmcraft.yaml",
                "name: test\n# a comment\nconfig:\n  options:\n    port:\n      type: int\n",
            )
        )
        assert node["name"].line == 1
        assert node["config"].line == 3
        assert node["config"]["options"]["port"].line == 5

    def test_line_survives_block_scalars(self, tmp_path: pathlib.Path):
        node = _yaml.load(
            _write(tmp_path, "charmcraft.yaml", "description: |\n  one\n  two\nname: test\n")
        )
        assert node["name"].line == 4

    @pytest.mark.parametrize(
        ("content", "reason"),
        [
            ("name: [unclosed\n", "expected"),
            ("- a\n- b\n", "top-level YAML value is not a mapping"),
            ("just a string\n", "top-level YAML value is not a mapping"),
            ("? [a, b]\n: c\n", "invalid mapping key"),
        ],
    )
    def test_broken_file_raises(self, tmp_path: pathlib.Path, content: str, reason: str):
        # A file that is there but broken must never be reported as missing.
        path = _write(tmp_path, "charmcraft.yaml", content)
        with pytest.raises(_yaml.FileLoadError) as excinfo:
            _yaml.load(path)
        assert excinfo.value.path == path
        assert reason in str(excinfo.value)

    def test_duplicate_keys_keep_the_last(self, tmp_path: pathlib.Path):
        # Matches PyYAML's own constructor.
        node = _yaml.load(_write(tmp_path, "charmcraft.yaml", "name: first\nname: second\n"))
        assert node["name"].value == "second"
        assert node["name"].line == 2

    def test_non_string_keys(self, tmp_path: pathlib.Path):
        # An unquoted ``on:`` is the boolean True under YAML 1.1. Rules have
        # to cope with that, so the loader must not assume string keys.
        node = _yaml.load(_write(tmp_path, "charmcraft.yaml", "on: allowed\n7: x\n"))
        assert node[True].value == "allowed"
        assert node[7].value == "x"
        assert list(node) == [True, 7]


class TestMerge:
    """Merging charmcraft.yaml with a legacy metadata.yaml."""

    def test_primary_wins_and_fallback_fills_in(self, tmp_path: pathlib.Path):
        primary = _yaml.load(_write(tmp_path, "charmcraft.yaml", "name: from-charmcraft\n"))
        fallback = _yaml.load(
            _write(tmp_path, "metadata.yaml", "name: from-metadata\nsummary: hi\n")
        )
        merged = _yaml.merge(primary, fallback)
        assert merged["name"].value == "from-charmcraft"
        assert merged["summary"].value == "hi"

    def test_merged_keys_keep_their_own_file(self, tmp_path: pathlib.Path):
        primary = _yaml.load(_write(tmp_path, "charmcraft.yaml", "name: test\ntype: charm\n"))
        fallback = _yaml.load(
            _write(tmp_path, "metadata.yaml", "summary: s\nseries:\n  - focal\n")
        )
        merged = _yaml.merge(primary, fallback)
        # The merged mapping as a whole still belongs to charmcraft.yaml...
        assert merged.source == "charmcraft.yaml"
        assert merged["name"].source == "charmcraft.yaml"
        # ...but each merged-in key names the file that declares it, which
        # is what lets a diagnostic anchor to the right line.
        assert merged["series"].source == "metadata.yaml"
        assert merged["series"].line == 2

    def test_absent_sides(self, tmp_path: pathlib.Path):
        primary = _yaml.load(_write(tmp_path, "charmcraft.yaml", "name: test\n"))
        absent = _yaml.load(tmp_path / "metadata.yaml")
        assert _yaml.merge(primary, absent)["name"].value == "test"
        assert _yaml.merge(absent, primary)["name"].value == "test"


class TestYamlNode:
    """The lookup behaviour rules rely on."""

    @pytest.fixture
    def node(self, tmp_path: pathlib.Path) -> Yaml:
        return _yaml.load(
            _write(
                tmp_path,
                "charmcraft.yaml",
                "name: test\nsummary:\nlinks:\n  issues: https://example.com\nseries: []\n",
            )
        )

    def test_get_missing_returns_absent_node(self, node: Yaml):
        missing = node.get("nope")
        assert not missing.present
        assert missing.line is None
        # An absent node still names a file, so a rule reporting the absence
        # can point at one.
        assert missing.source == "charmcraft.yaml"

    def test_present_distinguishes_null_from_missing(self, node: Yaml):
        # ``summary:`` with no value is present; a rule that cares about the
        # difference (an explicit ``default: ""`` is still a default) can ask.
        assert node.get("summary").present
        assert node.get("summary").value is None
        assert not node.get("nope").present

    def test_truthiness_is_the_value(self, node: Yaml):
        assert node.get("name")
        assert not node.get("summary")
        assert not node.get("nope")
        assert not node.get("series")

    def test_get_chains_through_missing_and_non_mappings(self, node: Yaml):
        assert node.get("links").get("issues").value == "https://example.com"
        # Neither a missing key nor a scalar raises when looked through.
        assert not node.get("nope").get("deeper").present
        assert not node.get("name").get("deeper").present

    def test_contains_and_iteration(self, node: Yaml):
        assert "summary" in node
        assert "nope" not in node
        assert list(node) == ["name", "summary", "links", "series"]

    def test_items_is_empty_for_a_non_mapping(self, node: Yaml):
        # This is what replaces the per-rule ``isinstance(..., dict)`` guards:
        # a malformed section yields no findings rather than a crash.
        assert list(node.get("series").items()) == []
        assert list(node.get("nope").items()) == []

    def test_getitem_raises_for_a_missing_key(self, node: Yaml):
        with pytest.raises(KeyError):
            node["nope"]
