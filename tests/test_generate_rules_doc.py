"""Tests for the RST-to-Markdown rewriting in ``tools/generate_rules_doc.py``."""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

_SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "tools" / "generate_rules_doc.py"
_spec = importlib.util.spec_from_file_location("generate_rules_doc", _SCRIPT)
assert _spec is not None and _spec.loader is not None
generate_rules_doc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(generate_rules_doc)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("plain *emphasis* stays", "plain *emphasis* stays"),
        ("a ``literal`` here", "a `literal` here"),
        ("a ``wrapped\n    literal`` here", "a `wrapped literal` here"),
        ("see :data:`_NAME`", "see `_NAME`"),
        ("see :class:`~ops.CharmBase`", "see `ops.CharmBase`"),
        ("say so once::\n\n    code", "say so once:\n\n    code"),
        ("Example ::\n\n    code", "Example\n\n    code"),
    ],
)
def test_markdown(text: str, expected: str):
    assert generate_rules_doc.markdown(text) == expected
