"""Publish what the agent job produced: the only step that writes to GitHub.

Runs in the publish job with the bot's token and no model. Everything the
agent job wrote is treated as untrusted, because the agent could have written
any of it:

- The commit to build on comes from the triage job, not from the agent.
- The patch is applied with ``git apply``, and then the *result* is checked:
  every changed path on the allowlist, ordinary files only (no symlinks,
  executables or submodules), and no new forbidden imports or calls in rule
  code or tests.
- Only the outcomes that the run's mode can produce are accepted.
- The commit message is rebuilt here. The PR text has raw HTML escaped, links
  off a short list, anything shaped like a secret, @-mentions and closing
  keywords removed, and
  ``Fixes #N`` is added here.
- Plans are posted inside a fenced block, so what a maintainer sees on the
  issue is exactly what a later run reads back.

    python3 publish.py --trigger DIR --agent DIR --agent-result RESULT --repo-dir CHECKOUT
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import urllib.parse
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from run import RULE_CODE, allowed_path, forbidden_uses  # ruff: ignore[E402]
from trigger import (  # ruff: ignore[E402]
    BUILT_MARKER,
    FAILED,
    LABEL,
    NEEDS_DESIGN,
    PLAN_MARKER,
    PLAN_ONLY,
    REVISION_MARKER,
    RUNNING,
)

REPO = os.environ.get("GITHUB_REPOSITORY", "")
SERVER = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
RUN_URL = f"{SERVER}/{REPO}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}"
DEFAULT_BRANCH = os.environ.get("DEFAULT_BRANCH", "main")
BOT_NAME = os.environ.get("AGENT_BOT_NAME") or "Prints Charming"
BOT_EMAIL = (
    os.environ.get("AGENT_BOT_EMAIL")
    or f"{os.environ.get('AGENT_BOT') or 'prints-charming-bot'}@users.noreply.github.com"
)
OUTCOMES = {
    "full": {"pr", "out_of_scope", "needs_design"},
    "plan-only": {"plan-only", "out_of_scope", "needs_design"},
    "revise": {"revision"},
}
LINK_HOSTS = {
    "github.com",
    "ubuntu.com",
    "canonical.com",
    "charmhub.io",
    "discourse.charmhub.io",
    "docs.python.org",
    "peps.python.org",
}
SECRET = re.compile(
    r"sk-or-v1-[0-9a-f]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"
    r"|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----"
)
# A closing keyword followed by anything GitHub reads as an issue: #N,
# owner/repo#N, GH-N or an issue or PR URL. The keyword goes; the reference stays.
CLOSING = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b\s*:?\s+"
    r"(?=\S{0,200}?(?:#\d|GH-\d|/issues/\d|/pull/\d))",
    re.I,
)
# Anything a browser or Markdown could read as a link: any http(s) scheme,
# whatever follows it (browsers read "https:evil.example" and "https:\\evil"
# as links to evil.example, and Markdown reads "https\:" as "https:"), a
# scheme-relative //host in any mix of slashes and backslashes, or a bare
# www. host.
URL = re.compile(r"\bhttps?\\?:[^\s)>\]]*|(?<![\w:])[/\\]{2}[^\s)>\]]+|\bwww\.[^\s)>\]]+", re.I)
MODEL = re.compile(r"[a-z0-9.-]+/[a-z0-9.:-]+")
STAGE = re.compile(r"[0-9]{2}-[a-z0-9-]+")
MAX_BODY = 60_000


def gh(*args: str) -> Any:
    out = subprocess.run(["gh", "api", *args], check=True, capture_output=True, text=True).stdout
    return json.loads(out) if out.strip() else None


def git(repo: pathlib.Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout


def comment(number: int, body: str) -> None:
    gh(f"repos/{REPO}/issues/{number}/comments", "-f", f"body={body[:MAX_BODY]}")


def set_labels(number: int, *, add: tuple[str, ...] = (), remove: tuple[str, ...] = ()) -> None:
    for label in remove:
        quoted = urllib.parse.quote(label, safe="")
        proc = subprocess.run(
            ["gh", "api", "-X", "DELETE", f"repos/{REPO}/issues/{number}/labels/{quoted}"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode and "404" not in proc.stderr:
            print(
                f"couldn't remove {label} from #{number}: {proc.stderr.strip()}", file=sys.stderr
            )
    if add:
        args = [a for lab in add for a in ("-f", f"labels[]={lab}")]
        gh("-X", "POST", f"repos/{REPO}/issues/{number}/labels", *args)


def clean_text(text: str, *, markdown: bool = True) -> str:
    """PR or comment text from the agent, made safe to post.

    Secrets and closing keywords are removed; ``&`` and ``<`` are escaped, so
    there is no raw HTML (hidden comments, ``<details>``, links) and no
    character references to spell a link or a mention with; links off the
    short list are removed; and a zero-width space after each ``@`` keeps a
    mention from notifying anyone. ``markdown=False`` is for plain text such
    as a title, which GitHub doesn't render as HTML.

    All of this applies inside code too. Deciding what GitHub will render as
    code takes a full CommonMark parser, and any text this got wrong would be
    posted unescaped, so a ``<`` in a code span shows as ``&lt;`` instead.
    """

    def link(match: re.Match) -> str:
        found = match.group(0)
        try:
            url = urllib.parse.urlsplit(found)
            ok = (
                found.lower().startswith("https://")
                and "\\" not in found
                and url.hostname in LINK_HOSTS
                and ".." not in url.path
                and "%2e" not in url.path.lower()
                and (url.hostname != "github.com" or url.path.startswith("/canonical/"))
            )
        except ValueError:  # not a URL urlsplit can read, such as "http://[::1"
            ok = False
        return found if ok else "(link removed)"

    # Cut first: GitHub won't take more, and the regexes below aren't all
    # linear on text an agent picked to be slow.
    text = SECRET.sub("(removed)", text[:MAX_BODY])
    text = CLOSING.sub("", text)
    if markdown:
        text = text.replace("&", "&amp;").replace("<", "&lt;")
    text = URL.sub(link, text)
    # An @-mention notifies whoever it names; keep the text, lose the ping.
    return re.sub(r"@(?=[A-Za-z0-9])", "@\u200b", text)


def footer(meta: dict) -> str:
    rows: dict[str, tuple[str, float]] = {}
    for call in meta.get("calls") or []:
        stage, model = str(call.get("stage", "")), str(call.get("model", ""))
        if not STAGE.fullmatch(stage) or not MODEL.fullmatch(model):
            continue
        name = re.sub(r"-\d+$", "", stage.split("-", 1)[1])
        cost = call.get("cost_usd")
        cost = float(cost) if isinstance(cost, (int, float)) else 0.0
        rows[name] = (model, rows.get(name, (model, 0.0))[1] + cost)
    lines = "\n".join(f"| {s} | `{m}` | ${c:.2f} |" for s, (m, c) in rows.items())
    total = sum(c for _, c in rows.values())
    return (
        "\n\n<details><summary>Agent run</summary>\n\n| Stage | Model | Cost |\n|---|---|---|\n"
        f"{lines}\n\nTotal ${total:.2f}, as the agent job reported it. "
        f"[Run log and stage outputs]({RUN_URL}).\n\n</details>\n"
    )


def plan_comment(agent: pathlib.Path, intro: str, *, built: bool = False) -> str:
    """The comment a later run reads the plan back from. BUILT for the plan a PR was made from."""
    # The plan is posted in a fence, which GitHub renders literally, so only
    # secrets need removing; anything more would change what is read back.
    plan = SECRET.sub("(removed)", (agent / "plan.md").read_text().strip())
    marker = f"{PLAN_MARKER}\n{BUILT_MARKER}" if built else PLAN_MARKER
    return (
        f"{marker}\n{intro}\n\n<details><summary>Plan</summary>\n\n"
        f"<!-- plan-start -->\n{fenced(plan, 'markdown')}\n<!-- plan-end -->\n\n</details>\n"
    )


def fenced(text: str, info: str = "") -> str:
    """TEXT in a backtick fence longer than any backtick run inside it, so it can't close early."""
    fence = "`" * max(4, max((len(m) for m in re.findall(r"`{3,}", text)), default=0) + 1)
    return f"{fence}{info}\n{text}\n{fence}"


def check_tree(repo: pathlib.Path, start: str) -> list[str]:
    """Problems with the applied change, read from git rather than from the patch."""
    problems = []
    raw = git(repo, "diff", "--cached", "--raw", "-z", "--no-renames", start)
    fields = raw.split("\0")
    for meta, path in zip(fields[0::2], fields[1::2], strict=False):
        if not meta:
            continue
        old_mode, new_mode, _, _, status = meta.lstrip(":").split()
        if re.search(r"[\x00-\x1f\x7f]", path):
            # Not echoed: the failure comment shows these, and a newline could
            # make one look like something else, such as a plan.
            problems.append(f"a path with control characters ({json.dumps(path)[:200]})")
            continue
        if status not in ("A", "M", "D"):
            problems.append(f"{path}: change type {status} isn't allowed")
        if {old_mode, new_mode} - {"000000", "100644"}:
            problems.append(f"{path}: mode {old_mode} -> {new_mode} isn't allowed")
        if not allowed_path(path):
            problems.append(f"{path}: outside what the agent may change")
        if status != "D" and new_mode == "100644" and path.endswith(".py"):
            # The staged blob, as bytes, which is how Python reads them (see
            # forbidden_uses). Not the work tree: a symlink there could point
            # at /dev/zero.
            source = subprocess.run(
                ["git", "show", f":{path}"], cwd=repo, capture_output=True, check=True
            ).stdout
            base = (
                b""
                if status == "A"
                else subprocess.run(
                    ["git", "show", f"{start}:{path}"], cwd=repo, capture_output=True, check=True
                ).stdout
            )
            rule_code = path.startswith(RULE_CODE)
            for line, what in forbidden_uses(source, base, rule_code=rule_code, path=path):
                problems.append(
                    f"{path}:{line}: {what} isn't allowed in {'rule code' if rule_code else 'tests'}"
                )
    return problems


def apply(repo: pathlib.Path, agent: pathlib.Path, trigger: dict, message: str) -> bool:
    """Commit the agent's change on top of the trigger's start commit. False if it's empty."""
    start, branch, new = trigger["start_sha"], trigger["branch"], trigger["mode"] != "revise"
    if not re.fullmatch(r"[0-9a-f]{40}", start):
        raise RuntimeError(f"unexpected start commit {start!r}")
    diff = (agent / "publish.diff").read_text() if (agent / "publish.diff").exists() else ""
    if not diff.strip():
        if new:
            raise RuntimeError("the change is empty")
        return False
    git(repo, "fetch", "--quiet", "origin", DEFAULT_BRANCH)
    if new:
        git(repo, "fetch", "--quiet", "origin", start)
        ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", start, f"origin/{DEFAULT_BRANCH}"],
            cwd=repo,
            check=False,
        )
        if ancestor.returncode:
            raise RuntimeError(f"{start} isn't on {DEFAULT_BRANCH}")
        git(repo, "checkout", "--quiet", "-b", branch, start)
    else:
        git(repo, "fetch", "--quiet", "origin", f"refs/heads/{branch}")
        git(repo, "checkout", "--quiet", "-B", branch, "FETCH_HEAD")
        if git(repo, "rev-parse", "HEAD").strip() != start:
            raise RuntimeError("the branch moved while the agent was working on it")
    patch = repo.parent / "publish.diff"
    patch.write_text(diff)
    git(repo, "apply", "--index", str(patch))
    problems = check_tree(repo, start)
    if problems:
        raise RuntimeError(
            "the change failed the publish checks:\n" + "\n".join(f"- {p}" for p in problems)
        )
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": BOT_NAME,
        "GIT_AUTHOR_EMAIL": BOT_EMAIL,
        "GIT_COMMITTER_NAME": BOT_NAME,
        "GIT_COMMITTER_EMAIL": BOT_EMAIL,
    }
    subprocess.run(["git", "commit", "--quiet", "-m", message], cwd=repo, env=env, check=True)
    git(repo, "push", "--quiet", "origin", f"HEAD:refs/heads/{branch}")
    return True


def commit_message(title: str, meta: dict, issue: int | None) -> str:
    models = sorted({
        str(c.get("model"))
        for c in meta.get("calls") or []
        if MODEL.fullmatch(str(c.get("model")))
    })
    trailers = "\n".join(f"Assisted-by: pi:{m.split('/')[-1]}" for m in models)
    fixes = f"Fixes #{issue}\n\n" if issue else ""
    return f"{title}\n\n{fixes}{trailers}\n"


def pr_title(agent: pathlib.Path) -> str:
    text = (agent / "title.txt").read_text() if (agent / "title.txt").exists() else ""
    title = next(iter(text.strip().splitlines()), "")
    # No "!" either: a rule PR from an issue isn't a breaking change.
    title = re.sub(r"[^\w\s:().,`'/-]", "", clean_text(title, markdown=False))[:100].strip()
    # The repository's PR title check: a known type, no scope.
    types = r"(?:chore|ci|docs|feat|fix|perf|refactor|revert|test)"
    return title if re.match(rf"^{types}: \S", title) else f"feat: {title or 'new rule'}"


def pr_body(agent: pathlib.Path, meta: dict, issue: int) -> str:
    body = clean_text((agent / "pr.md").read_text().strip()) if (agent / "pr.md").exists() else ""
    body = re.sub(r"\n*#\d+\s*$", "", body.strip())  # what's left of a closing line
    # Said here as well as in the agent's text, which might leave it out.
    unreviewed = (
        "\n\n**Not fully reviewed:** at least one of the agent's review passes "
        "produced no usable output, so this change has had less checking than usual."
        if meta.get("unreviewed")
        else ""
    )
    return body[: MAX_BODY - 2000] + unreviewed + footer(meta) + f"\nFixes #{issue}\n"


def publish(args: argparse.Namespace, trigger: dict) -> None:
    issue, mode = trigger["issue"], trigger["mode"]
    revising = mode == "revise"
    target = trigger["pr"] if revising else issue
    meta_path = args.agent / "meta.json"
    try:
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    except ValueError:
        meta = {}
    meta = meta if isinstance(meta, dict) else {}
    outcome = str(meta.get("outcome") or "")
    if outcome not in OUTCOMES[mode]:
        reason = "the agent job didn't finish" if args.agent_result != "success" else "no result"
        if re.fullmatch(r"[a-z_-]{1,40}", outcome):
            reason = f"`{outcome}`"
        fail(target, f"{reason}.", issue=not revising)
        return
    if outcome == "plan-only":
        comment(
            issue,
            plan_comment(
                args.agent,
                f"Here's the plan. Edit it in this comment if it needs changing, then label "
                f"the issue `{LABEL}` to implement it.",
            ),
        )
        set_labels(issue, remove=(PLAN_ONLY,))
    elif outcome in ("out_of_scope", "needs_design"):
        verdict = (
            "doesn't belong in charmlint"
            if outcome == "out_of_scope"
            else "needs a design decision first"
        )
        comment(
            issue,
            plan_comment(
                args.agent,
                f"The agent thinks this {verdict}; the plan says why. To go ahead anyway, change "
                f"the plan's verdict to `PROCEED` in this comment"
                + (f", remove the `{NEEDS_DESIGN}` label" if outcome == "needs_design" else "")
                + f" and label the issue `{LABEL}`. Labelling it without changing the verdict "
                "makes a new plan.",
            ),
        )
        set_labels(
            issue,
            add=(NEEDS_DESIGN,) if outcome == "needs_design" else (),
            remove=(LABEL, PLAN_ONLY),
        )
    elif outcome == "pr":
        title = pr_title(args.agent)
        body = pr_body(args.agent, meta, issue)
        plan = plan_comment(args.agent, "The plan the agent's PR was built from.", built=True)
        apply(args.repo_dir, args.agent, trigger, commit_message(title, meta, issue))
        comment(issue, plan)
        gh(
            f"repos/{REPO}/pulls",
            "-f",
            f"title={title}",
            "-f",
            f"head={trigger['branch']}",
            "-f",
            f"base={DEFAULT_BRANCH}",
            "-f",
            f"body={body}",
            "-F",
            # Always a draft: CONTRIBUTING.md asks for a person to review a
            # tool-written PR before it leaves draft.
            "draft=true",
        )
        set_labels(issue, remove=(LABEL,))
    else:  # revision
        text = (
            (args.agent / "revision-comment.md").read_text()
            if (args.agent / "revision-comment.md").exists()
            else "The agent revised the change."
        )
        # Everything that could fail is done before the push: a commit without
        # its marker comment would let the same review be acted on again.
        text, end = clean_text(text.strip()), footer(meta)
        changed = apply(
            args.repo_dir, args.agent, trigger, commit_message("chore: address review", meta, None)
        )
        note = "" if changed else "\n\nNo code changed in this revision."
        comment(target, f"{REVISION_MARKER}\n{text}{note}{end}")


def fail(number: int, why: str, *, issue: bool) -> None:
    comment(number, f"The agent run stopped: {why} [Run log]({RUN_URL}).")
    if issue:
        set_labels(number, add=(FAILED,), remove=(LABEL, PLAN_ONLY))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trigger", type=pathlib.Path, required=True)
    parser.add_argument("--agent", type=pathlib.Path, required=True)
    parser.add_argument("--agent-result", required=True)
    parser.add_argument("--repo-dir", type=pathlib.Path, required=True)
    args = parser.parse_args()
    args.repo_dir = args.repo_dir.resolve()
    trigger = json.loads((args.trigger / "trigger.json").read_text())
    if not trigger["run"]:
        notice = trigger.get("notice")
        if notice:
            comment(notice["number"], notice["body"])
            set_labels(notice["number"], remove=tuple(notice.get("remove") or ()))
        return 0
    revising = trigger["mode"] == "revise"
    target = trigger["pr"] if revising else trigger["issue"]
    try:
        publish(args, trigger)
    except Exception as e:  # ruff: ignore[BLE001] - every failure is reported on the issue
        detail = e.stderr if isinstance(e, subprocess.CalledProcessError) else str(e)
        print(f"publish failed: {type(e).__name__}: {detail}", file=sys.stderr)
        try:
            # In a fence, which GitHub renders literally, so only secrets need removing.
            why = SECRET.sub("(removed)", str(detail)).strip()[:1500]
            fail(target, f"publishing failed.\n\n{fenced(why)}\n", issue=not revising)
        except Exception as e2:  # ruff: ignore[BLE001]
            print(f"couldn't report the failure: {e2}", file=sys.stderr)
        return 1
    finally:
        set_labels(trigger["issue"], remove=(RUNNING,))
    return 0


if __name__ == "__main__":
    sys.exit(main())
