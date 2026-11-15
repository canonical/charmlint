"""The import and call checks that the pipeline and the publish job share."""

from __future__ import annotations

import pytest
from run import allowed_path, forbidden_uses


def whats(source: str, base: str = "", *, rule_code: bool = True) -> list[str]:
    path = "src/charmlint/_rules/new.py" if rule_code else "tests/test_new.py"
    return [what for _, what in forbidden_uses(source, base, rule_code=rule_code, path=path)]


@pytest.mark.parametrize(
    "source",
    [
        "import ast\nimport yaml\nfrom charmlint import _ast\nimport urllib.parse\n",
        "from . import _base\n",
        "from .. import _ast, _yaml\nfrom ._base import Rule\nfrom .. import _models as models\n",
        "from charmlint._rules._base import Rule\n",
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
        ("from subprocess import run\n", "`from subprocess import run`"),
        ("from charmlint import _cli\n", "`from charmlint import _cli`"),
        ("from .._cli import main\n", "`from charmlint._cli import main`"),
        (
            "from charmlint._rules.charmcraft_compat import os\n",
            "`from charmlint._rules.charmcraft_compat import os`",
        ),
        ("import yaml\nyaml.unsafe_load(x)\n", "`.unsafe_load`"),
        ("import yaml\nyaml.load(x, Loader=yaml.Loader)\n", "`.Loader`"),
        ("import pathlib\npathlib.os.system('x')\n", "`.os`"),
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


@pytest.mark.parametrize(
    ("source", "what"),
    [
        ("from urllib import request\n", "`from urllib import request`"),
        ("from http import client\n", "`from http import client`"),
        ("from .test_cli import subprocess\n", "`from tests.test_cli import subprocess`"),
        ("import inspect\n", "`import inspect`"),
    ],
)
def test_tests_forbidden(source: str, what: str) -> None:
    assert what in whats(source, rule_code=False)


def test_tests_may_use_harmless_parts_of_a_package() -> None:
    assert whats("import urllib.parse\nurllib.parse.quote('x')\n", rule_code=False) == []


def test_new_calls_through_an_existing_import_are_reported() -> None:
    base = "import os\n\nos.access('x', os.X_OK)\n"
    assert whats(base + "os.system('x')\n", base) == ["`os.system`"]
    assert whats(base + "os.access('y', os.X_OK)\n", base) == ["`os.X_OK`", "`os.access`"]


def test_uses_already_in_the_file_are_not_reported() -> None:
    base = "import subprocess\n"
    assert whats(base + "X = 1\n", base, rule_code=False) == []


@pytest.mark.parametrize("encoding", ["utf-7", "shift_jis", "latin-1"])
def test_coding_declarations_other_than_utf8_are_reported(encoding: str) -> None:
    # In UTF-7 the second line is `import subprocess`; as UTF-8 it's a comment.
    source = f"# coding: {encoding}\n# +AAo-import subprocess\n".encode()
    assert forbidden_uses(source, rule_code=False) == [
        (1, "a coding declaration other than UTF-8")
    ]


def test_utf8_bytes_are_checked_like_text() -> None:
    assert forbidden_uses(b"# coding: utf-8\nimport os\n") == [(2, "`import os`")]
    assert forbidden_uses(b"\xef\xbb\xbfimport os\n") == [(1, "`import os`")]
    assert forbidden_uses(b"x = 1\0\n") == [(0, "source that doesn't parse on this Python")]


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
