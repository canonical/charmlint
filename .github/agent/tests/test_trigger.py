"""Triage: who may start a run, and what the scheduled run picks up."""

from __future__ import annotations

import pathlib

import pytest
import trigger


@pytest.fixture(autouse=True)
def allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(trigger, "ALLOWLIST", {"maintainer"})
    monkeypatch.setattr(trigger, "REPO", "canonical/charmlint")


def test_allowed_is_case_insensitive() -> None:
    assert trigger.allowed("Maintainer")
    assert not trigger.allowed("someone")
    assert not trigger.allowed(None)


def pr(**overrides: object) -> dict:
    return {
        "head": {"ref": "agent/issue-12", "repo": {"full_name": "canonical/charmlint"}},
        "user": {"login": trigger.BOT},
        "state": "open",
        **overrides,
    }


def review(**overrides: object) -> dict:
    return {"state": "CHANGES_REQUESTED", "user": {"login": "maintainer"}, **overrides}


def test_check_review_accepts_a_maintainers_change_request() -> None:
    assert trigger.check_review(pr(), review()) == 12


@pytest.mark.parametrize(
    ("pr_", "review_"),
    [
        (pr(head={"ref": "feature", "repo": {"full_name": "canonical/charmlint"}}), review()),
        (pr(head={"ref": "agent/issue-12", "repo": {"full_name": "fork/charmlint"}}), review()),
        (pr(user={"login": "someone"}), review()),
        (pr(), review(state="COMMENTED")),
        (pr(), review(user={"login": "someone"})),
        (pr(state="closed"), review()),
    ],
)
def test_check_review_refuses(pr_: dict, review_: dict) -> None:
    with pytest.raises(trigger.Skip):
        trigger.check_review(pr_, review_)


def test_strip_markup() -> None:
    assert trigger.strip_markup("<!-- hidden -->Fix <b>this</b>") == "Fix this"


def test_snapshot_keeps_only_allowlisted_comments_from_before_approval(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    comments = [
        {"user": {"login": "maintainer"}, "created_at": "2026-01-01T00:00:00Z", "body": "a"},
        {"user": {"login": "someone"}, "created_at": "2026-01-01T00:00:00Z", "body": "b"},
        {"user": {"login": "maintainer"}, "created_at": "2026-01-03T00:00:00Z", "body": "c"},
    ]
    monkeypatch.setattr(trigger, "gh", lambda *a, **k: comments)
    issue = {"number": 1, "title": "t", "body": None, "labels": [{"name": "agent"}]}
    trigger.snapshot(issue, "2026-01-02T00:00:00Z", tmp_path)
    task = (tmp_path / "task.json").read_text()
    assert '"body": "a"' in task
    assert '"body": "b"' not in task
    assert '"body": "c"' not in task


def issue(number: int, label: str) -> dict:
    return {"number": number, "labels": [{"name": label}]}


@pytest.fixture
def queue(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Two waiting issues: #1 full, approved first, and #2 plan-only."""
    state: dict = {"open_prs": 0, "ran": None}
    by_label = {
        trigger.LABEL: [issue(1, trigger.LABEL)],
        trigger.PLAN_ONLY: [issue(2, trigger.PLAN_ONLY)],
    }
    at = {1: "2026-01-01T00:00:00Z", 2: "2026-01-02T00:00:00Z"}

    def gh(path: str, **_: object) -> list[dict]:
        return next(v for k, v in by_label.items() if f"labels={k}&" in path)

    monkeypatch.setattr(trigger, "gh", gh)
    monkeypatch.setattr(trigger, "open_bot_prs", lambda: [{}] * state["open_prs"])
    monkeypatch.setattr(trigger, "approval", lambda n, label: {"at": at[n], "issue": {}})
    monkeypatch.setattr(trigger, "check_not_edited", lambda *a: None)
    monkeypatch.setattr(trigger, "branch_exists", lambda n: False)

    def issue_run(number: int, mode: str, out: pathlib.Path, *, approved: dict) -> dict:
        state["ran"] = (number, mode)
        return {}

    monkeypatch.setattr(trigger, "issue_run", issue_run)
    return state


def test_drain_takes_the_oldest_approval(queue: dict, tmp_path: pathlib.Path) -> None:
    trigger.drain(tmp_path)
    assert queue["ran"] == (1, "full")


def test_drain_takes_plan_only_issues_when_prs_are_full(
    queue: dict, tmp_path: pathlib.Path
) -> None:
    queue["open_prs"] = trigger.MAX_OPEN
    trigger.drain(tmp_path)
    assert queue["ran"] == (2, "plan-only")


@pytest.mark.parametrize(
    ("actor", "triggering"),
    [("someone", "someone"), ("maintainer", "someone"), ("someone", "maintainer")],
)
def test_dispatch_needs_both_actors_on_the_allowlist(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path, actor: str, triggering: str
) -> None:
    # A re-run keeps GITHUB_ACTOR from the first attempt; GITHUB_TRIGGERING_ACTOR
    # is whoever clicked re-run.
    monkeypatch.setenv("GITHUB_ACTOR", actor)
    monkeypatch.setenv("GITHUB_TRIGGERING_ACTOR", triggering)
    with pytest.raises(trigger.Skip, match="allowlist"):
        trigger.dispatched({"inputs": {"mode": "full", "issue": "12"}}, tmp_path)


def labelled(label: str, at: str, by: str = "github-actions[bot]") -> dict:
    return {"event": "labeled", "label": {"name": label}, "actor": {"login": by}, "created_at": at}


def test_run_started_is_when_triage_marked_the_issue_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timeline = [
        labelled(trigger.LABEL, "2026-01-01T10:00:00Z", "maintainer"),
        labelled(trigger.RUNNING, "2026-01-01T10:01:00Z"),
        labelled(trigger.RUNNING, "2026-01-01T11:00:00Z", "someone"),
        labelled(trigger.RUNNING, "2026-01-03T00:00:00Z"),  # a later run
    ]
    monkeypatch.setattr(trigger, "gh", lambda *a, **k: timeline)
    assert trigger.run_started(12, "2026-01-01T12:00:00Z") == "2026-01-01T10:01:00Z"
    with pytest.raises(trigger.Skip):
        trigger.run_started(12, "2026-01-01T09:00:00Z")


def test_an_edit_during_the_run_stops_a_revision_and_says_so_on_the_pr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    edits = {"data": {"repository": {"issue": {"userContentEdits": {"nodes": [
        {"editedAt": "2026-01-01T10:30:00Z", "editor": {"login": "someone"}},
    ]}}}}}  # fmt: skip
    monkeypatch.setattr(trigger, "gh", lambda *a, **k: edits if a[0] == "graphql" else [])
    with pytest.raises(trigger.Skip) as e:
        trigger.check_not_edited(12, "2026-01-01T10:01:00Z", "Why.", notify=20)
    assert e.value.notice == {
        "number": 20,
        "body": "#12 was edited after it was approved, so the agent didn't run. Why.",
        "remove": [],
    }
