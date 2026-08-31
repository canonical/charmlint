"""Tests for charmlint._toml."""

import pathlib

import pytest

from charmlint import _toml
from charmlint._linter import build_context
from charmlint._yaml import FileLoadError


class TestLoad:
    """Loading a charm's TOML files."""

    def test_absent_file(self, tmp_path: pathlib.Path):
        assert _toml.load(tmp_path / "pyproject.toml") is None

    def test_empty_file(self, tmp_path: pathlib.Path):
        path = tmp_path / "pyproject.toml"
        path.write_text("")
        # Present but declaring nothing is not the same as absent.
        assert _toml.load(path) == {}

    def test_parses_tables(self, tmp_path: pathlib.Path):
        path = tmp_path / "pyproject.toml"
        path.write_text('[project]\nname = "x"\ndependencies = ["ops>=2.17,<4"]\n')
        data = _toml.load(path)
        assert data is not None
        assert data["project"]["name"] == "x"
        assert data["project"]["dependencies"] == ["ops>=2.17,<4"]

    def test_malformed_raises(self, tmp_path: pathlib.Path):
        path = tmp_path / "pyproject.toml"
        path.write_text("this is [not valid toml\n")
        with pytest.raises(FileLoadError) as excinfo:
            _toml.load(path)
        assert excinfo.value.path == path
        assert "could not parse" in excinfo.value.reason

    def test_unreadable_raises(self, tmp_path: pathlib.Path):
        path = tmp_path / "pyproject.toml"
        path.mkdir()
        with pytest.raises(FileLoadError) as excinfo:
            _toml.load(path)
        assert "could not read" in excinfo.value.reason


class TestContext:
    """The parsed pyproject.toml reaching rules through the context."""

    def test_context_carries_pyproject(self, tmp_charm: pathlib.Path):
        (tmp_charm / "pyproject.toml").write_text('[project]\nname = "x"\n')
        context = build_context(tmp_charm)
        assert context.pyproject == {"project": {"name": "x"}}

    def test_context_pyproject_none_when_absent(self, tmp_charm: pathlib.Path):
        assert build_context(tmp_charm).pyproject is None
