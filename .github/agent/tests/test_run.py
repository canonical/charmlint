"""The import and call checks that the pipeline and the publish job share."""

from __future__ import annotations

import pytest
from run import allowed_path, forbidden_uses


def whats(source: str, base: str = "", *, rule_code: bool = True) -> list[str]:
    return [what for _, what in forbidden_uses(source, base, rule_code=rule_code)]


@pytest.mark.parametrize(
    "source",
    [
        "import ast\nimport yaml\nfrom charmlint import _ast\nimport urllib.parse\n",
        "from . import _base\n",
        "CHECK = 'exec'\nd = {'exec': 1}\n",
    ],
)
def test_rule_code_allowed(source: str) -> None:
    assert whats(source) == []


@pytest.mark.parametrize(
    ("source", "what"),
    [
        ("import os\n", "`import os`"),
        ("import urllib.request\n", "`import urllib.request`"),
        ("from subprocess import run\n", "`import subprocess`"),
        ("exec('x')\n", "`exec()`"),
        ("__import__('os')\n", "`__import__()`"),
        ("x = ().__class__.__subclasses__\n", "`.__subclasses__`"),
        ("x = __builtins__\n", "`__builtins__`"),
    ],
)
def test_rule_code_forbidden(source: str, what: str) -> None:
    assert what in whats(source)


def test_tests_may_import_what_rules_may_not() -> None:
    assert whats("import pytest\nimport pathlib\n", rule_code=False) == []
    assert whats("import os.path\n", rule_code=False) == ["`import os.path`"]


def test_uses_already_in_the_file_are_not_reported() -> None:
    base = "import subprocess\n"
    assert whats(base + "X = 1\n", base, rule_code=False) == []


def test_source_that_does_not_parse_is_reported() -> None:
    assert whats("import subprocess\ndef (:\n") == ["source that doesn't parse on this Python"]


@pytest.mark.parametrize(
    ("path", "ok"),
    [
        ("src/charmlint/_rules/foo.py", True),
        ("src/charmlint/_ast.py", True),
        ("src/charmlint/_ast.pyc", False),
        ("tests/test_foo.py", True),
        ("tests/test_foo.txt", False),
        ("tests/data/charm/metadata.yaml", False),
        ("tests/../pyproject.py", False),
        ("src/charmlint/_rules/__pycache__/pebble.cpython-312.pyc", False),
        ("src/charmlint/_rules/__pycache__/pebble.py", False),
        ("src/charmlint/_rules/pebble.abi3.so", False),
        ("docs/rules.md", True),
        ("docs/corpus.md", False),
        ("RULES_TRACKER.md", False),
        (".github/agent/publish.py", False),
        ("pyproject.toml", False),
    ],
)
def test_allowed_path(path: str, ok: bool) -> None:
    assert allowed_path(path) is ok
