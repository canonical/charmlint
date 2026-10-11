"""Tests for charmlint._discovery."""

import pathlib

from charmlint._discovery import discover_charms, is_charm_dir
from tests.conftest import write_charmcraft_yaml


def _charm(directory: pathlib.Path, name: str) -> pathlib.Path:
    """Create a charm directory with metadata and a src/ tree."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "src").mkdir(exist_ok=True)
    write_charmcraft_yaml(directory, {"name": name})
    return directory


class TestIsCharmDir:
    def test_charmcraft_yaml(self, tmp_path: pathlib.Path):
        assert is_charm_dir(_charm(tmp_path / "c", "c"))

    def test_metadata_yaml(self, tmp_path: pathlib.Path):
        (tmp_path / "metadata.yaml").write_text("name: legacy\n")
        assert is_charm_dir(tmp_path)

    def test_neither(self, tmp_path: pathlib.Path):
        assert not is_charm_dir(tmp_path)


class TestDiscoverCharms:
    def test_root_is_the_charm(self, tmp_path: pathlib.Path):
        _charm(tmp_path, "solo")
        assert discover_charms(tmp_path) == [tmp_path]

    def test_no_charm_anywhere(self, tmp_path: pathlib.Path):
        (tmp_path / "docs").mkdir()
        assert discover_charms(tmp_path) == []

    def test_finds_nested_charms_outermost_first(self, tmp_path: pathlib.Path):
        _charm(tmp_path / "charms" / "beta", "beta")
        _charm(tmp_path / "charms" / "alpha", "alpha")
        assert discover_charms(tmp_path) == [
            tmp_path / "charms" / "alpha",
            tmp_path / "charms" / "beta",
        ]

    def test_finds_charms_three_levels_down(self, tmp_path: pathlib.Path):
        # sunbeam-charms keeps its cinder backends at charms/storage/<name>.
        nested = _charm(tmp_path / "charms" / "storage" / "cinder-volume-ceph", "cvc")
        assert discover_charms(tmp_path) == [nested]

    def test_stops_below_the_depth_cap(self, tmp_path: pathlib.Path):
        _charm(tmp_path / "a" / "b" / "c" / "d", "too-deep")
        assert discover_charms(tmp_path) == []

    def test_does_not_descend_into_a_charm(self, tmp_path: pathlib.Path):
        # A reactive charm's built layer puts a second metadata.yaml under
        # src/; the charm at the root is the one the user means.
        root = _charm(tmp_path, "reactive")
        write_charmcraft_yaml(root / "src", {"name": "reactive"})
        assert discover_charms(tmp_path) == [root]

    def test_ignores_test_fixture_charms(self, tmp_path: pathlib.Path):
        root = _charm(tmp_path / "charms" / "real", "real")
        _charm(tmp_path / "tests" / "integration" / "tester", "tester")
        assert discover_charms(tmp_path) == [root]

    def test_ignores_dotted_directories(self, tmp_path: pathlib.Path):
        # .tox/**/site-packages holds more charm-shaped files across the
        # Hyrum cache than every real nested charm combined.
        _charm(tmp_path / ".tox" / "unit" / "pkg", "vendored")
        assert discover_charms(tmp_path) == []

    def test_ignores_build_output(self, tmp_path: pathlib.Path):
        _charm(tmp_path / "build" / "charm", "built")
        _charm(tmp_path / "thing.egg-info" / "charm", "packaged")
        assert discover_charms(tmp_path) == []

    def test_ignores_symlinked_directories(self, tmp_path: pathlib.Path):
        real = _charm(tmp_path / "elsewhere" / "charm", "real")
        (tmp_path / "link").symlink_to(real.parent)
        assert discover_charms(tmp_path) == [real]
