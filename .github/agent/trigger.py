"""Decide whether the agent runs, on what, and snapshot its inputs.

Runs in the triage job, with a read-only token plus ``issues: write`` (to mark
an issue as running) and ``actions: write`` (to start a revision run). Nothing
here calls a model. Writes into ``--out``:

- ``trigger.json``: ``run``, ``mode`` (``full``, ``plan-only`` or ``revise``),
  ``issue``, ``pr``, ``branch``, ``start_sha`` (the commit the agent starts
  from, which the publish job builds on), ``reason`` and an optional
  ``notice`` (``{"number": N, "body": "..."}``) for the publish job to post.
- ``task.json``: the issue as approved (title, body, labels, and comments by
  allowlisted users made before the approval), without HTML comments, which
  whoever approved it couldn't see.
- ``plan.md``: a plan posted earlier by the agent, if there is one.
- ``feedback.md``: the review to address, for a revision.

and sets ``run``, ``notice``, ``issue``, ``mode``, ``start_sha`` and ``attempt``
(the run attempt these were decided in) as step outputs.

Approval is the ``agent`` (or ``agent:plan-only``) label applied by someone in
``AGENT_ALLOWLIST``, read from the issue's timeline rather than from the event,
so the scheduled drain checks it the same way. An issue whose title or body
someone else changed after approval is not run: whoever approved it read a
different text.

A review event doesn't run the agent itself. It starts a manual run of this
workflow on the default branch, which checks the review again, so revisions
run with the same environments and cache scope as everything else.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import pathlib
import re
import subprocess
import sys
import urllib.parse
from typing import Any

LABEL = "agent"
PLAN_ONLY = "agent:plan-only"
RUNNING = "agent:running"
FAILED = "agent:failed"
PLAN_MARKER = "<!-- charmlint-agent:plan -->"
# On the second line of the plan comment posted with a PR: that plan has been
# implemented, so a later full run plans again rather than reusing it.
BUILT_MARKER = "<!-- charmlint-agent:built -->"
REVISION_MARKER = "<!-- charmlint-agent:revision -->"
NEEDS_DESIGN = "needs design"
MAX_REVISIONS = 3
BRANCH = re.compile(r"^agent/issue-(\d+)$")
VERDICT = re.compile(r"\b(PROCEED|OUT_OF_SCOPE|NEEDS_DESIGN)\b", re.I)
PLAN_BLOCK = re.compile(
    r"<!-- plan-start -->\n(`{3,})markdown\n(.*?)\n\1\n<!-- plan-end -->", re.S
)

REPO = os.environ.get("GITHUB_REPOSITORY", "")
DEFAULT_BRANCH = os.environ.get("DEFAULT_BRANCH", "main")
WORKFLOW = os.environ.get("AGENT_WORKFLOW", "agent.yaml")
ALLOWLIST = {
    u.strip().lower() for u in os.environ.get("AGENT_ALLOWLIST", "").split(",") if u.strip()
}
BOT = (os.environ.get("AGENT_BOT") or "prints-charming-bot").lower()
MAX_OPEN = int(os.environ.get("AGENT_MAX_OPEN_PRS") or 2)


class Skip(Exception):
    """Nothing to run; the message says why."""

    def __init__(self, reason: str, notice: dict | None = None) -> None:
        super().__init__(reason)
        self.notice = notice


def gh(*args: str, paginate: bool = False) -> Any:
    cmd = ["gh", "api", *args]
    if paginate:
        cmd[2:2] = ["--paginate", "--jq", ".[]"]
        out = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
        # Not splitlines(): that also splits on characters JSON leaves raw
        # inside strings (U+0085, U+2028), which anyone can put in a title.
        return [json.loads(line) for line in out.split("\n") if line]
    return json.loads(
        subprocess.run(cmd, check=True, capture_output=True, text=True).stdout or "null"
    )


def allowed(login: str | None) -> bool:
    return bool(login) and login.lower() in ALLOWLIST


def approval(number: int, label: str) -> dict:
    """The latest time an allowlisted user applied LABEL, if the label is still on."""
    issue = gh(f"repos/{REPO}/issues/{number}")
    if label not in {lab["name"] for lab in issue["labels"]}:
        raise Skip(f"#{number} doesn't have the {label} label")
    events = [
        e
        for e in gh(f"repos/{REPO}/issues/{number}/timeline", paginate=True)
        if e.get("event") == "labeled" and e.get("label", {}).get("name") == label
    ]
    if not events or not allowed(events[-1].get("actor", {}).get("login")):
        raise Skip(f"#{number}: the {label} label wasn't applied by an allowlisted user")
    return {"issue": issue, "at": events[-1]["created_at"], "by": events[-1]["actor"]["login"]}


def check_not_edited(number: int, since: str, why: str, *, notify: int | None = None) -> None:
    """Refuse if anyone outside the allowlist changed the title or body after SINCE.

    The notice goes on NOTIFY (the issue by default) and ends with WHY.
    """
    owner, name = REPO.split("/")
    data = gh(
        "graphql",
        "-f",
        "query=query($o:String!,$n:String!,$i:Int!){repository(owner:$o,name:$n){issue(number:$i)"
        f"{{{EDITS}}}}}}}",
        "-f",
        f"o={owner}",
        "-f",
        f"n={name}",
        "-F",
        f"i={number}",
    )
    late = [
        e
        for e in edits_of(data["data"]["repository"]["issue"])
        if e["editedAt"] > since and not allowed((e["editor"] or {}).get("login"))
    ]
    renames = [
        e
        for e in gh(f"repos/{REPO}/issues/{number}/timeline", paginate=True)
        if e.get("event") == "renamed"
        and e["created_at"] > since
        and not allowed(e.get("actor", {}).get("login"))
    ]
    if late or renames:
        raise Skip(
            f"#{number} was edited after approval",
            {
                "number": notify or number,
                "body": f"#{number} was edited after it was approved, so the agent didn't run. "
                f"{why}".strip(),
                "remove": [] if notify else [LABEL, PLAN_ONLY],
            },
        )


# The newest 100 edits: the connection is newest first.
EDITS = "userContentEdits(first:100){pageInfo{hasNextPage} nodes{editedAt editor{login}}}"


def edits_of(node: dict) -> list[dict]:
    """The edits in NODE's EDITS connection.

    With more than 100, the oldest can't be seen, and one is made up that
    counts as an edit by someone else just now: refusing is safer than
    guessing.
    """
    connection = node["userContentEdits"]
    edits = list(connection["nodes"])
    if connection["pageInfo"]["hasNextPage"]:
        edits.append({"editedAt": "9999", "editor": None})
    return edits


def snapshot(issue: dict, before: str, out: pathlib.Path) -> list[dict]:
    """Write task.json: the issue as whoever approved it saw it. Returns its comments."""
    comments = gh(f"repos/{REPO}/issues/{issue['number']}/comments", paginate=True)
    kept = []
    for c in comments:
        if not (
            allowed(c["user"]["login"])
            and c["created_at"] <= before
            and PLAN_MARKER not in c["body"]
        ):
            continue
        # Anyone with write access can edit a maintainer's comment. Only an
        # edited one costs a request.
        if c.get("updated_at") != c["created_at"] and not edits_allowed(c):
            print(
                f"a comment by {c['user']['login']} was edited by someone not on the allowlist",
                file=sys.stderr,
            )
            continue
        kept.append({"author": c["user"]["login"], "body": visible(c["body"])})
    task = {
        "issue": issue["number"],
        "title": issue["title"],
        "body": visible(issue["body"]),
        "labels": [lab["name"] for lab in issue["labels"] if not lab["name"].startswith(LABEL)],
        "comments": kept,
    }
    (out / "task.json").write_text(json.dumps(task, indent=2) + "\n")
    return comments


def edits_allowed(comment: dict) -> bool:
    """Whether everyone who edited COMMENT (anything with a ``node_id``) is allowlisted, or the bot."""
    data = gh(
        "graphql",
        "-f",
        f"query=query($id:ID!){{node(id:$id){{... on Comment{{{EDITS}}}}}}}",
        "-f",
        f"id={comment['node_id']}",
    )
    return all(
        allowed((e["editor"] or {}).get("login"))
        or (e["editor"] or {}).get("login", "").lower() == BOT
        for e in edits_of(data["data"]["node"])
    )


def visible(text: str | None) -> str:
    """TEXT without its HTML comments, which GitHub doesn't show to whoever approves it.

    An unclosed comment hides everything after it. Each one leaves a note, so
    a reader of the task can tell something was there.
    """
    return re.sub(r"<!--.*?(?:-->|\Z)", "(HTML comment removed)", text or "", flags=re.S).strip()


def find_plan(comments: list[dict], out: pathlib.Path, *, revising: bool = False) -> bool:
    """The plan from the agent's latest plan comment, as a maintainer may have edited it.

    Only a comment that starts with the marker: a failure comment quotes
    text the agent chose, which could contain one. And only if nobody
    outside the allowlist has edited it, since anyone with write access can.

    A revision uses the plan its PR was built from. A new run doesn't: that
    PR was closed, so it plans again. Nor does it use a plan whose verdict
    isn't ``PROCEED``: approving the issue again without changing the verdict
    asks for a fresh look, at an issue that has probably changed.
    """
    plans = [
        c
        for c in comments
        if c["user"]["login"].lower() == BOT and c["body"].startswith(PLAN_MARKER)
    ]
    if not plans:
        return False
    body = plans[-1]["body"].replace("\r\n", "\n")
    if not revising and body.startswith(f"{PLAN_MARKER}\n{BUILT_MARKER}"):
        return False
    if not edits_allowed(plans[-1]):
        print(
            "the latest plan comment was edited by someone not on the allowlist", file=sys.stderr
        )
        return False
    match = PLAN_BLOCK.search(body)
    if not match:
        return False
    plan = match.group(2).strip() + "\n"
    if not revising and parse_verdict(plan) != "PROCEED":
        return False
    (out / "plan.md").write_text(plan)
    return True


def parse_verdict(plan: str) -> str:
    """The plan's verdict, however it's marked up; NEEDS_DESIGN if it can't be read.

    Not PROCEED: a plan whose verdict can't be read goes back to a maintainer
    rather than being implemented. The verdict is what the first line with
    any text after "Verdict" starts with, and that line may name only one.
    The template's own line of all three (``PROCEED | OUT_OF_SCOPE |
    NEEDS_DESIGN``) is skipped, so a plan that leaves it in place above its
    answer isn't read as the first of them.
    """
    match = re.search(r"Verdict\b(.*)", plan, re.I | re.S)
    for line in match.group(1).splitlines() if match else ():
        named = {v.upper() for v in VERDICT.findall(line)}
        if len(named) == 3 or not re.search(r"\w", line):
            continue
        first = re.match(rf"\W*{VERDICT.pattern}", line, re.I)
        return first.group(1).upper() if first and len(named) == 1 else "NEEDS_DESIGN"
    return "NEEDS_DESIGN"


def in_flight() -> int:
    """Agent PRs open, plus issues with a run in progress that may open one.

    An issue whose PR is open and being revised is counted once.
    """
    prs = {int(m.group(1)) for p in open_bot_prs() if (m := BRANCH.match(p["head"]["ref"]))}
    running = {
        i["number"]
        for i in gh(f"repos/{REPO}/issues?state=open&labels={RUNNING}&per_page=100", paginate=True)
    }
    return len(prs | running)


def open_bot_prs() -> list[dict]:
    return [
        p
        for p in gh(f"repos/{REPO}/pulls?state=open&per_page=100", paginate=True)
        if p["user"]["login"].lower() == BOT and BRANCH.match(p["head"]["ref"])
    ]


def branch_exists(number: int) -> bool:
    proc = subprocess.run(
        ["gh", "api", f"repos/{REPO}/branches/agent/issue-{number}"],
        capture_output=True,
        text=True,
    )
    if proc.returncode and "404" not in proc.stderr:
        raise RuntimeError(f"couldn't check for agent/issue-{number}: {proc.stderr.strip()}")
    return proc.returncode == 0


def default_head() -> str:
    return gh(f"repos/{REPO}/commits/{DEFAULT_BRANCH}")["sha"]


def issue_run(number: int, mode: str, out: pathlib.Path, *, approved: dict | None) -> dict:
    label = PLAN_ONLY if mode == "plan-only" else LABEL
    approved = approved or approval(number, label)
    issue = approved["issue"]
    if issue.get("pull_request") or issue["state"] != "open":
        raise Skip(f"#{number} is not an open issue")
    labels = {lab["name"] for lab in issue["labels"]}
    if RUNNING in labels:
        raise Skip(f"#{number} already has a run in progress")
    if NEEDS_DESIGN in labels:
        raise Skip(
            f"#{number} is labelled {NEEDS_DESIGN}",
            {
                "number": number,
                "body": f"This issue is labelled `{NEEDS_DESIGN}`, so the agent didn't run. "
                f"Remove that label once the design is settled, and label the issue `{label}` "
                "again.",
                "remove": [label],
            },
        )
    # Before the capacity check, so an issue left waiting is told now.
    check_not_edited(number, approved["at"], f"Remove and re-apply `{label}` to approve it.")
    if mode == "full":
        if branch_exists(number):
            raise Skip(
                f"agent/issue-{number} already exists",
                {
                    "number": number,
                    "body": f"The branch `agent/issue-{number}` is left from an earlier run, so "
                    f"the agent didn't run. Delete it and label the issue `{LABEL}` again.",
                    "remove": [LABEL],
                },
            )
        if in_flight() >= MAX_OPEN:
            raise Skip(
                f"{MAX_OPEN} agent PRs are already open or being made; "
                f"the scheduled run will pick #{number} up later"
            )
    comments = snapshot(issue, approved["at"], out)
    has_plan = mode == "full" and find_plan(comments, out)
    return {
        "run": True,
        "mode": mode,
        "issue": number,
        "plan": has_plan,
        "start_sha": default_head(),
        "reason": f"#{number} approved by {approved['by']} at {approved['at']}",
    }


def drain(out: pathlib.Path) -> dict:
    """The oldest approved issue that hasn't run.

    Plan-only issues are included: a label event whose triage was still
    pending when another one queued was cancelled, and this is its retry.
    """
    modes = [(PLAN_ONLY, "plan-only")]
    if in_flight() < MAX_OPEN:
        modes.append((LABEL, "full"))
    candidates = []
    notice = None
    for label, mode in modes:
        for issue in gh(
            f"repos/{REPO}/issues?state=open&labels={label}&per_page=100", paginate=True
        ):
            # Not agent:failed: a failed run removes the approval label, so an
            # issue that has both was approved again.
            labels = {lab["name"] for lab in issue["labels"]}
            if issue.get("pull_request") or labels & {RUNNING, NEEDS_DESIGN}:
                continue
            try:
                approved = approval(issue["number"], label)
                # Checked here too, so one edited issue can't block the queue.
                check_not_edited(
                    issue["number"],
                    approved["at"],
                    f"Remove and re-apply `{label}` to approve it.",
                )
            except Skip as e:
                notice = notice or e.notice
                continue
            if mode == "plan-only" or not branch_exists(issue["number"]):
                candidates.append((approved["at"], issue["number"], mode, approved))
    if not candidates:
        # One notice a run; each removes its issue's label, so the next run
        # gets to the next one.
        raise Skip("no approved issues waiting", notice)
    _, number, mode, approved = min(candidates)
    return issue_run(number, mode, out, approved=approved)


def check_review(pr: dict, review: dict) -> int:
    """The issue number, for a changes-requested review of an agent PR by an allowlisted user."""
    match = BRANCH.match(pr["head"]["ref"])
    if not match or pr["user"]["login"].lower() != BOT or pr["head"]["repo"]["full_name"] != REPO:
        raise Skip("not an agent PR")
    if review["state"].lower() != "changes_requested" or not allowed(review["user"]["login"]):
        raise Skip("not a changes-requested review from an allowlisted reviewer")
    if pr["state"] != "open":
        raise Skip("PR is closed")
    return int(match.group(1))


def queue_revision(event: dict) -> dict:
    check_review(event["pull_request"], event["review"])
    gh(
        "-X",
        "POST",
        f"repos/{REPO}/actions/workflows/{WORKFLOW}/dispatches",
        "-f",
        f"ref={DEFAULT_BRANCH}",
        "-f",
        "inputs[mode]=revise",
        "-f",
        f"inputs[pr]={event['pull_request']['number']}",
        "-f",
        f"inputs[review]={event['review']['id']}",
    )
    raise Skip(f"revision of #{event['pull_request']['number']} queued on {DEFAULT_BRANCH}")


def revision(number: int, review_id: int, out: pathlib.Path) -> dict:
    pr = gh(f"repos/{REPO}/pulls/{number}")
    review = gh(f"repos/{REPO}/pulls/{number}/reviews/{review_id}")
    issue_number = check_review(pr, review)
    done = [
        c
        for c in gh(f"repos/{REPO}/issues/{number}/comments", paginate=True)
        # Starts with, as for a plan: a failure comment quotes the agent's text.
        if c["user"]["login"].lower() == BOT and c["body"].startswith(REVISION_MARKER)
    ]
    # A review is acted on once: replaying an old one would run the agent on
    # feedback a maintainer has already seen answered.
    if any(c["created_at"] > review["submitted_at"] for c in done):
        raise Skip(f"review {review_id} has already been addressed")
    if len(done) >= MAX_REVISIONS:
        raise Skip(
            "revision limit reached",
            {
                "number": number,
                "body": f"This PR has had {MAX_REVISIONS} agent revisions, so the agent won't "
                "revise it again. Push changes to the branch directly, or close it.",
            },
        )
    # Not the review's own comments endpoint, which leaves out the line numbers.
    inline = [
        c
        for c in gh(f"repos/{REPO}/pulls/{number}/comments?per_page=100", paginate=True)
        if c.get("pull_request_review_id") == review_id
    ]
    # Anyone with write access can edit a reviewer's comments.
    edited = [c for c in inline if c.get("updated_at") != c["created_at"]]
    if not all(edits_allowed(c) for c in [review, *edited]):
        raise Skip(
            f"review {review_id} was edited by someone not on the allowlist",
            {
                "number": number,
                "body": "This review was edited by someone who isn't on the agent's allowlist, "
                "so the agent didn't act on it. Submit a new review to request the changes.",
            },
        )
    parts = [visible(review["body"])] if visible(review["body"]) else []
    parts += [inline_feedback(c) for c in inline]
    if not parts:
        raise Skip("the review has no comments to act on")
    (out / "feedback.md").write_text("\n\n---\n\n".join(parts) + "\n")
    issue = gh(f"repos/{REPO}/issues/{issue_number}")
    if RUNNING in {lab["name"] for lab in issue["labels"]}:
        raise Skip(
            f"#{issue_number} already has a run in progress",
            {
                "number": number,
                "body": "The agent is already working on this PR, so it didn't start on this "
                "review. Request changes again once it has posted its revision.",
            },
        )
    # The PR was built from the issue as it was approved; an edit since, by
    # someone else, isn't something a maintainer read.
    check_not_edited(
        issue_number,
        run_started(issue_number, pr["created_at"]),
        "Push changes to the branch directly, or close this PR and approve the issue again.",
        notify=number,
    )
    comments = snapshot(issue, pr["created_at"], out)
    if not find_plan(comments, out, revising=True):
        raise Skip(
            "no plan comment found",
            {
                "number": number,
                "body": f"The agent couldn't find its plan on #{issue_number}, "
                "so it didn't revise.",
            },
        )
    return {
        "run": True,
        "mode": "revise",
        "issue": issue_number,
        "pr": number,
        "plan": True,
        "branch": pr["head"]["ref"],
        "start_sha": pr["head"]["sha"],
        "reason": f"review {review_id} by {review['user']['login']}",
    }


def inline_feedback(comment: dict) -> str:
    """One inline review comment, with where it was left and the code it was left on."""
    line = comment.get("line") or comment.get("original_line")
    where = f"`{comment['path']}`" + (f" line {line}" if line else "")
    if comment.get("line") is None and line:
        where += " (as it was when reviewed; the code has changed since)"
    # The end of the hunk is the commented line and the few above it.
    hunk = "\n".join((comment.get("diff_hunk") or "").splitlines()[-4:])
    fence = "`" * max(3, max((len(m) for m in re.findall(r"`+", hunk)), default=0) + 1)
    code = f"\n\n{fence}diff\n{hunk}\n{fence}" if hunk else ""
    return f"On {where}:{code}\n\n{visible(comment['body'])}"


def run_started(number: int, before: str) -> str:
    """When triage started the run that opened a PR at BEFORE.

    That's when it added agent:running, straight after checking the issue
    for edits since its approval.
    """
    started = [
        e["created_at"]
        for e in gh(f"repos/{REPO}/issues/{number}/timeline", paginate=True)
        if e.get("event") == "labeled"
        and e.get("label", {}).get("name") == RUNNING
        and (e.get("actor") or {}).get("login") == "github-actions[bot]"
        and e["created_at"] <= before
    ]
    if not started:
        raise Skip(f"no run of #{number} found before {before}")
    return max(started)


def numeric(value: str | None) -> bool:
    """Whether a workflow_dispatch input, which is always a string, holds a number."""
    return bool(value) and value.strip().isdigit()


def dispatched(event: dict, out: pathlib.Path) -> dict:
    inputs = event.get("inputs") or {}
    mode = inputs.get("mode") or "full"
    if mode == "revise":
        # Started by queue_revision (as github-actions[bot]) or by a maintainer;
        # the review is checked too.
        triggering = os.environ.get("GITHUB_TRIGGERING_ACTOR") or os.environ.get("GITHUB_ACTOR")
        if triggering != "github-actions[bot]" and not allowed(triggering):
            raise Skip("revision started by someone not on the allowlist")
        if not (numeric(inputs.get("pr")) and numeric(inputs.get("review"))):
            raise Skip("a revision needs both a pr and a review number")
        return revision(int(inputs["pr"]), int(inputs["review"]), out)
    # A re-run keeps the original run's GITHUB_ACTOR, and approval is as of
    # now, so whoever started this attempt has to be on the allowlist too.
    actor = os.environ.get("GITHUB_ACTOR")
    triggering = os.environ.get("GITHUB_TRIGGERING_ACTOR") or actor
    if not (allowed(actor) and allowed(triggering)):
        raise Skip("dispatched or re-run by someone not on the allowlist")
    if not numeric(inputs.get("issue")):
        raise Skip("no issue number given")
    number = int(inputs["issue"])
    issue = gh(f"repos/{REPO}/issues/{number}")
    now = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return issue_run(number, mode, out, approved={"issue": issue, "at": now, "by": triggering})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=pathlib.Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    name = os.environ["GITHUB_EVENT_NAME"]
    event = json.loads(pathlib.Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    try:
        if name == "issues":
            label = event["label"]["name"]
            if label not in (LABEL, PLAN_ONLY):
                raise Skip(f"label {label} isn't ours")
            mode = "plan-only" if label == PLAN_ONLY else "full"
            result = issue_run(event["issue"]["number"], mode, args.out, approved=None)
        elif name == "workflow_dispatch":
            result = dispatched(event, args.out)
        elif name == "schedule":
            result = drain(args.out)
        elif name == "pull_request_review":
            result = queue_revision(event)
        else:
            raise Skip(f"event {name} isn't handled")
        if not re.fullmatch(r"[0-9a-f]{40}", result["start_sha"]):
            raise Skip(f"unexpected start commit {result['start_sha']!r}")
        # On the issue for revisions too, so a second review waits for this one.
        gh(
            "-X",
            "POST",
            f"repos/{REPO}/issues/{result['issue']}/labels",
            "-f",
            f"labels[]={RUNNING}",
        )
        if result["mode"] == "full":
            # A run that's approved again after one failed.
            subprocess.run(
                [
                    "gh",
                    "api",
                    "-X",
                    "DELETE",
                    f"repos/{REPO}/issues/{result['issue']}/labels/{urllib.parse.quote(FAILED, safe='')}",
                ],
                capture_output=True,
                check=False,
            )
    except Skip as e:
        result = {"run": False, "reason": str(e), "notice": e.notice}
    if result.get("issue") and not result.get("branch"):
        result["branch"] = f"agent/issue-{result['issue']}"
    (args.out / "trigger.json").write_text(json.dumps(result, indent=2) + "\n")
    print(result["reason"])
    with open(os.environ.get("GITHUB_OUTPUT", os.devnull), "a") as f:
        f.write(f"run={'true' if result['run'] else 'false'}\n")
        f.write(f"notice={'true' if result.get('notice') else 'false'}\n")
        f.write(f"issue={result.get('issue') or ''}\n")
        f.write(f"mode={result.get('mode') or ''}\n")
        f.write(f"start_sha={result.get('start_sha') or ''}\n")
        # The agent and publish jobs only run in the attempt that triage did:
        # "Re-run failed jobs" would reuse these outputs without the checks.
        f.write(f"attempt={os.environ.get('GITHUB_RUN_ATTEMPT', '')}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
