"""The import and call checks that the pipeline and the publish job share."""

from __future__ import annotations

import pytest
from run import (
    allowed_path,
    counts_block,
    finding_delta,
    forbidden_uses,
    kept_findings,
    make_title,
    new_crashes,
)


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


def row(
    rule: str = "R-001", charm: str = "c", path: str = "a.py", line: int | None = 1, **kw: str
) -> dict:
    return {"rule_id": rule, "charm": charm, "path": path, "line": line, "message": "m", **kw}


def changes(base: list[dict], cand: list[dict]) -> list[tuple]:
    return sorted(
        (r["change"], r["rule_id"], r["charm"], r["line"]) for r in finding_delta(base, cand)
    )


def test_a_reworded_message_is_not_a_change() -> None:
    base = [row(line=n) for n in range(5)]
    assert changes(base, [row(line=n, message="new wording") for n in range(5)]) == []


def test_findings_added_and_removed_are_changes() -> None:
    base = [row(line=1), row(line=2)]
    cand = [row(line=2, message="reworded"), row(line=3)]
    assert changes(base, cand) == [("added", "R-001", "c", 3), ("removed", "R-001", "c", 1)]


def test_a_charm_that_now_crashes_is_left_out() -> None:
    base = [row(charm="c", line=n) for n in range(18)] + [row(charm="d")]
    cand = [row(rule="CRASH", charm="c", line=None, message="KeyError: x")]
    assert changes(base, cand) == [("removed", "R-001", "d", 1)]
    assert [r["charm"] for r in new_crashes(base, cand)] == ["c"]


PLAN = "- ID: `CHARMCRAFT-004`\n- Name: `unknown-top-level-field`\n"


def test_title_adds_a_new_rule_and_updates_an_existing_one() -> None:
    assert make_title(PLAN, set()) == "feat: add CHARMCRAFT-004 (unknown-top-level-field)"
    assert make_title(PLAN, {"CHARMCRAFT-004"}) == (
        "fix: update CHARMCRAFT-004 (unknown-top-level-field)"
    )


def test_a_changed_rule_is_counted_by_everything_it_still_reports() -> None:
    # An FP fix: three findings on main, one removed, two kept (one of them still an FP).
    base = [row(line=n) for n in (1, 2, 3)]
    cand = [row(line=n) for n in (1, 2)]
    delta = finding_delta(base, cand)
    rows = delta + kept_findings(base, cand, delta)
    labels = {("removed", 3): "TP", ("kept", 1): "TP", ("kept", 2): "FP"}
    classified = [dict(r, severity="warning", label=labels[r["change"], r["line"]]) for r in rows]
    block = counts_block({"charms": 10, "fatal": 0}, classified)
    assert "2 findings, all warning, 0 of them new. 1 findings no longer reported." in block
    assert "| R-001 | 1 | 0 | 1 | 0 | 2 |" in block
    assert "**Totals: 2 findings, 1 FP (50%).**" in block
