"""Replay the getting-started tutorial and check that charmlint's output matches it.

The tutorial shows charmlint's exact output at each step, so a new rule or a
changed message would silently make it wrong. This test follows the page
block by block, applying each edit as a reader would, and fails if any
sample output no longer matches. When it does, update the tutorial in the
same change.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from charmlint._cli import main

_TUTORIAL = (
    pathlib.Path(__file__).resolve().parent.parent / "docs" / "tutorial" / "getting-started.md"
)

_FENCE = re.compile(r"^```(\w+)\n(.*?)^```$", re.MULTILINE | re.DOTALL)

# Whole-file blocks, in the order the tutorial creates the files.
_NEW_FILES = {"yaml": "charmcraft.yaml", "toml": "pyproject.toml", "python": "src/charm.py"}


def _blocks() -> list[tuple[str, str]]:
    return [(m.group(1), m.group(2)) for m in _FENCE.finditer(_TUTORIAL.read_text())]


def _replace_option(charmcraft_yaml: str, snippet: str) -> str:
    """Replace a config option in charmcraft.yaml with the tutorial's edited version.

    The snippet is the option as the reader should leave it, possibly with
    a comment line above it. Everything from the option's key line down to
    the next line at the same or a lower indent is replaced.
    """
    snippet_lines = snippet.splitlines()
    key = next(line for line in snippet_lines if not line.lstrip().startswith("#"))
    lines = charmcraft_yaml.splitlines()
    start = lines.index(key)
    indent = len(key) - len(key.lstrip())
    end = start + 1
    while end < len(lines) and len(lines[end]) - len(lines[end].lstrip()) > indent:
        end += 1
    return "\n".join([*lines[:start], *snippet_lines, *lines[end:]]) + "\n"


def _set_charmlint_table(pyproject: str, table: str) -> str:
    """Add the ``[tool.charmlint]`` table, or replace it if it's already there."""
    before, _, _ = pyproject.partition("[tool.charmlint]")
    return before.rstrip("\n") + "\n\n" + table


def test_tutorial_outputs_match(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.delenv("NO_COLOR", raising=False)
    charm = tmp_path / "my-charm"
    created: set[str] = set()
    exit_code: int | None = None
    runs = 0

    for lang, body in _blocks():
        if lang == "text":
            command, _, expected = body.partition("\n")
            if body == "$ mkdir -p my-charm/src\n$ cd my-charm\n":
                (charm / "src").mkdir(parents=True)
                monkeypatch.chdir(charm)
            elif body == "$ chmod +x src/charm.py\n":
                (charm / "src" / "charm.py").chmod(0o755)
            elif command == "$ uvx charmlint":
                capsys.readouterr()
                exit_code = main([])
                # The terminal shows both streams; a clean run's summary is on stderr.
                captured = capsys.readouterr()
                assert captured.out + captured.err == expected, f"output of run {runs + 1}"
                summary = expected.rstrip("\n").rsplit("\n", 1)[-1]
                assert exit_code == (1 if " error" in summary else 0), summary
                runs += 1
            elif command == "$ echo $?":
                assert exit_code == int(expected)
            else:
                pytest.fail(f"the test doesn't know how to run:\n{body}")
        elif lang in _NEW_FILES and _NEW_FILES[lang] not in created:
            path = charm / _NEW_FILES[lang]
            path.write_text(body)
            created.add(_NEW_FILES[lang])
        elif lang == "yaml":
            path = charm / "charmcraft.yaml"
            path.write_text(_replace_option(path.read_text(), body))
        elif lang == "toml" and body.startswith("[tool.charmlint]"):
            path = charm / "pyproject.toml"
            path.write_text(_set_charmlint_table(path.read_text(), body))
        else:
            pytest.fail(f"the test doesn't know what to do with this {lang} block:\n{body}")

    # Five sample outputs at the time of writing; fewer means the parsing missed some.
    assert runs >= 5
