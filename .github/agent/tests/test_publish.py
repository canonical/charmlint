"""The publish job's checks on what the agent produced."""

from __future__ import annotations

import pathlib
import subprocess

import publish
import pytest
import trigger

# ---- clean_text ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("a <b>bold</b> & more", "a &lt;b>bold&lt;/b> &amp; more"),
        ("thanks @someone", "thanks `@someone`"),
        ("Fixes #12", "#12"),
        ("closes: canonical/charmlint#3", "canonical/charmlint#3"),
        ("ghp_" + "a" * 36, "(removed)"),
        ("sk-or-v1-" + "0" * 40, "(removed)"),
    ],
)
def test_clean_text_prose(text: str, expected: str) -> None:
    assert publish.clean_text(text) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/canonical/charmlint/pull/1",
        "https://canonical.com/juju/docs/juju-cli/latest/reference/hook/#install",
        "https://charmhub.io/postgresql",
    ],
)
def test_clean_text_keeps_allowed_links(url: str) -> None:
    assert publish.clean_text(f"see {url} now") == f"see {url} now"


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example/x",
        "http://github.com/canonical/charmlint",
        "https://github.com/someone-else/repo",
        "https:evil.example",
        "https:\\\\evil.example",
        "https://ubuntu.com/../x",
        "https://ubuntu.com/%2e%2e/x",
        "//evil.example/x",
        "www.evil.example",
    ],
)
def test_clean_text_removes_other_links(url: str) -> None:
    assert publish.clean_text(f"see {url} now") == "see (link removed) now"


def test_clean_text_leaves_code_literal() -> None:
    text = "a `<b>@x</b>` b\n\n```\n<img src=https://evil.example> @someone\n```\n"
    assert publish.clean_text(text) == text


def test_clean_text_code_span_does_not_cross_a_blank_line() -> None:
    # GitHub ends the paragraph at the blank line, so these backticks are not
    # a code span and the middle paragraph is rendered.
    text = "`x\n\n<img src=https://evil.example/p.png> @someone\n\ny`"
    cleaned = publish.clean_text(text)
    assert "<img" not in cleaned
    assert "evil.example" not in cleaned
    assert "`@someone`" in cleaned


def test_clean_text_plain_text_is_not_escaped() -> None:
    assert publish.clean_text("a < b & c", markdown=False) == "a < b & c"


# ---- fences ---------------------------------------------------------------------


@pytest.mark.parametrize("text", ["plain", "```\nx\n```", "`````\ny\n`````", "````"])
def test_fenced_cannot_be_closed_from_inside(text: str) -> None:
    out = publish.fenced(text)
    fence = out.splitlines()[0]
    assert set(fence) == {"`"}
    assert out == f"{fence}\n{text}\n{fence}"
    assert all(not line.startswith(fence) for line in text.splitlines())


def test_plan_round_trips_through_the_issue_comment(tmp_path: pathlib.Path) -> None:
    plan = "# Plan\n\n````python\nx = 1\n````\n\n```\ny\n```\n\nVerdict: PROCEED"
    (tmp_path / "plan.md").write_text(plan)
    body = publish.plan_comment(tmp_path, "intro")
    # A maintainer's edit in the browser comes back with CRLF line endings.
    comments = [{"user": {"login": trigger.BOT}, "body": body.replace("\n", "\r\n")}]
    assert trigger.find_plan(comments, tmp_path)
    assert (tmp_path / "plan.md").read_text() == plan + "\n"


# ---- pr_title -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("feat: add FOO-001 (foo)", "feat: add FOO-001 (foo)"),
        ("fix!: stop reporting bar", "fix: stop reporting bar"),
        ("add a rule", "feat: add a rule"),
        ("feat(rules): scoped", "feat: feat(rules): scoped"),
        ("", "feat: new rule"),
        ("feat: <b>x</b> @y", "feat: bx/b `y`"),
    ],
)
def test_pr_title(tmp_path: pathlib.Path, title: str, expected: str) -> None:
    (tmp_path / "title.txt").write_text(title + "\n")
    assert publish.pr_title(tmp_path) == expected


# ---- check_tree -----------------------------------------------------------------


def git(repo: pathlib.Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@invalid", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


@pytest.fixture
def repo(tmp_path: pathlib.Path) -> tuple[pathlib.Path, str]:
    git(tmp_path, "init", "-q")
    rules = tmp_path / "src/charmlint/_rules"
    rules.mkdir(parents=True)
    (rules / "existing.py").write_text("import re\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_old.py").write_text("import subprocess\n")
    (tmp_path / "README.md").write_text("hi\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "start")
    return tmp_path, git(tmp_path, "rev-parse", "HEAD").strip()


def staged_problems(repo: tuple[pathlib.Path, str]) -> list[str]:
    path, start = repo
    git(path, "add", "-A")
    return publish.check_tree(path, start)


def test_check_tree_accepts_a_rule_and_its_test(repo: tuple[pathlib.Path, str]) -> None:
    path, _ = repo
    (path / "src/charmlint/_rules/new.py").write_text("import ast\nimport yaml\n")
    (path / "tests/test_new.py").write_text("import pathlib\n")
    (path / "tests/test_old.py").write_text("import subprocess\n\nX = 1\n")
    assert staged_problems(repo) == []


def test_check_tree_rejects_paths_off_the_allowlist(repo: tuple[pathlib.Path, str]) -> None:
    path, _ = repo
    (path / "README.md").write_text("changed\n")
    (path / "RULES_TRACKER.md").write_text("new\n")
    problems = staged_problems(repo)
    assert any(p.startswith("README.md:") for p in problems)
    assert any(p.startswith("RULES_TRACKER.md:") for p in problems)


def test_check_tree_rejects_symlinks_and_executables(repo: tuple[pathlib.Path, str]) -> None:
    path, _ = repo
    (path / "tests/link").symlink_to("/etc/passwd")
    script = path / "tests/run.sh"
    script.write_text("#!/bin/sh\n")
    script.chmod(0o755)
    problems = staged_problems(repo)
    assert any("tests/link: mode" in p for p in problems)
    assert any("tests/run.sh: mode" in p for p in problems)


def test_check_tree_rejects_new_imports(repo: tuple[pathlib.Path, str]) -> None:
    path, _ = repo
    (path / "src/charmlint/_rules/existing.py").write_text("import re\nimport os\n")
    (path / "tests/test_new.py").write_text("from subprocess import run\n")
    problems = staged_problems(repo)
    assert any("existing.py:2: `import os` isn't allowed in rule code" in p for p in problems)
    assert any("test_new.py:1: `import subprocess` isn't allowed in tests" in p for p in problems)


def test_check_tree_rejects_source_that_does_not_parse(repo: tuple[pathlib.Path, str]) -> None:
    path, _ = repo
    (path / "src/charmlint/_rules/new.py").write_text("import subprocess\ndef (:\n")
    problems = staged_problems(repo)
    assert any("doesn't parse" in p for p in problems)
