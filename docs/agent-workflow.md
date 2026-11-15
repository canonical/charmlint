# The agent workflow

An agent turns approved issues into pull requests, and revises its own pull requests after review. It runs in GitHub Actions with open-weight models through OpenRouter. It opens PRs as `prints-charming-bot`, and a maintainer reviews and merges them like any other PR. The code is in `.github/agent/`, and the workflows are `.github/workflows/agent.yaml` and `.github/workflows/agent-weekly.yaml`.

## Using it

Label an issue `agent` to approve it. The agent plans the change, implements it, measures it over the charm corpus, reviews it, and opens a PR. The PR is always a draft, because CONTRIBUTING.md asks for a person to review a tool-written PR before it leaves draft; the PR body lists any review finding or possible miss that is still open.

Label an issue `agent:plan-only` to see the plan first. The agent posts the plan as a comment and stops. Edit the plan in that comment if it needs changing, then label the issue `agent` to implement it. The same works when the agent decides an issue is out of scope or needs a design decision: it posts the plan with that verdict, and changing the verdict to `PROCEED` before labelling the issue `agent` again overrides it. For a design decision the agent also adds the `needs design` label, and it won't run on an issue that has it, so remove that label too. Only edits by allowlisted users count.

Labelling an issue `agent` again makes a new plan unless the latest plan comment says `PROCEED` and hasn't been implemented. So after the agent's PR is closed, or after a verdict that nobody changed, the agent plans from the issue as it is now.

To revise a PR, submit a review that requests changes. The agent addresses the review comments, measures and reviews the change again, pushes a new commit and comments with what it did. It revises a PR at most three times. The review event itself only starts a run of the workflow on the default branch, so a revision runs with the same credentials and checks as a new PR.

Only labels and reviews from users in the `AGENT_ALLOWLIST` variable count. If someone else edits the issue after it's labelled, the agent doesn't run, and comments to say so. The same goes for revisions: an edit since the run that opened the PR stops them, with a comment on the PR, and so does a review that someone else edited. The agent reads the issue without its HTML comments, which whoever approved it couldn't see, and leaves out a maintainer's comment that someone else edited.

At most `AGENT_MAX_OPEN_PRS` agent PRs are open or being made at a time. An issue labelled while that many are open waits. A scheduled run twice a day picks up the oldest waiting issue, including a plan-only one. It also catches labels that GitHub dropped: only one triage runs at a time, and GitHub keeps only the newest one waiting, so labelling several issues at once can leave some for the scheduled run.

The workflow can also be run by hand, with an issue number, from the Actions tab. "Re-run failed jobs" does nothing for a run of this workflow: the agent and publish jobs only run in the attempt that triage ran in, so that each run is checked. Use "Re-run all jobs", or label the issue again.

When a run fails, the agent comments on the issue with a link to the run, removes `agent` and adds `agent:failed`. Every stage's prompt, transcript and output is kept as an artefact of the run for 90 days. If the publish job itself is cancelled or times out, `agent:running` stays on the issue and nothing will run it again; remove that label by hand.

## How it runs

The workflow has three jobs.

| Job | Credentials | What it does |
|---|---|---|
| triage | read-only token, plus adding `agent:running` | Checks who applied the label and whether the issue changed since, and snapshots the issue. No model. |
| agent | the OpenRouter key, held by a proxy | Runs the pipeline. No GitHub write access. |
| publish | the bot's token | Checks the patch, commits it as the bot, pushes `agent/issue-N` and opens the PR. No model. |

The pipeline and every tool the models use run as an `agent` user, in a systemd unit of their own. That user has no `sudo`, `cron` or `at`, can't see other users' processes or read the runner's home directory, and gets none of the job's tokens. Once its Python environments are installed, its firewall rules let it reach only the key proxy on localhost, not even DNS. The pipeline's unit also has a cgroup filter that allows only localhost, because harden-runner keeps inserting ACCEPT rules above the agent's chain while the job runs. The job checks both before the pipeline starts, and that the `agent` user can't write to any directory on `PATH`, where it could leave a command for a later step to run. When the pipeline ends, the job stops the unit and fails if any `agent` process is left. The agent user packs its own outputs, and the runner unpacks them, so no root process copies from a directory the agent controls.

The OpenRouter key is held by a proxy that runs as a third user and reads the key from standard input. The proxy only forwards the configured models, pinned to their first-party providers. Each request reserves a worst-case cost before it is sent, and the proxy refuses requests once the run's spending and reservations reach one and a half times `AGENT_BUDGET_USD`.

Because the agent could write any of the agent job's output, the publish job checks all of it. It builds on the commit triage recorded, not one the agent names. It applies the patch and then checks the result: only the rule code, tests and `docs/rules.md` may change, and only as ordinary files. Rule code may only import a short list of modules, and new tests may not import modules such as `subprocess` or `os`, because they run in CI on the bot's PR. These checks catch the obvious cases; a maintainer's review is still what stops harmful code. It writes the commit message itself. In the PR text it escapes raw HTML, and removes links to unexpected sites, anything shaped like a secret, @-mentions and closing keywords, and then adds `Fixes #N` itself. Plans are posted inside a fenced block, so what a maintainer reads on the issue is exactly what a later run uses.

| Item | Answer |
|---|---|
| Trigger | An allowlisted maintainer's `agent` or `agent:plan-only` label, the scheduled drain, a changes-requested review from an allowlisted reviewer, or a manual run |
| Permissions | Agent job: `contents: read` and the OpenRouter key through a proxy. Publish job: the bot's token, scoped to this repository |
| Data boundary | Public only: charmlint, its public issues, and the public charm corpus |
| Models | GLM 5.3 and Kimi K2.7 through OpenRouter, pinned to their first-party providers |
| Spending limit | The OpenRouter key's credit limit, and `AGENT_BUDGET_USD` per run (default $8), enforced by the key proxy |
| Timeout | `timeout-minutes` on each job, and bounded fix rounds in the pipeline |
| Failure behaviour | A comment on the issue with the run link, and the `agent:failed` label. Nothing else is blocked |
| Audit trail | The Actions log, every stage's outputs as artefacts, and a link to the run in each PR |
| Human approval | A label before any work, and a maintainer's review and merge after |

## The corpus

The agent measures every rule over the same charm corpus that [corpus.md](corpus.md) describes. A weekly workflow clones the charms in hyrum's charm list (pinned to a commit in `agent-weekly.yaml`, and bumped by hand), drops build output and large files, and stores the result in the Actions cache. The agent job uses the newest copy.

## Setting it up

1. Give `prints-charming-bot` write access to the repository.
2. Create a fine-grained token for the bot with access to this repository only, and contents, pull requests and issues read and write. Don't give it the workflows or administration permissions. Set it to expire in 90 days.
3. Create two environments, both restricted to the default branch:
   - `agent-llm`, with an `OPENROUTER_API_KEY` secret. Give the key a credit limit and a 90-day expiry.
   - `agent-publish`, with the bot's token as `AGENT_PAT`.
4. Set these repository variables:
   - `AGENT_ALLOWLIST`: GitHub logins whose labels and reviews count, separated by commas.
   - `AGENT_BOT`: the bot's login (`prints-charming-bot`).
   - `AGENT_BOT_NAME` and `AGENT_BOT_EMAIL`: the commit author for the bot's commits. Use the bot's `noreply` address.
   - `AGENT_MAX_OPEN_PRS` (optional, default 2) and `AGENT_BUDGET_USD` (optional, default 8; a hard issue costs $6-8). The models each stage uses are set in `.github/agent/run.py`, and the key proxy forwards exactly those.
   - `AGENT_MIN_CHARMS` (optional, default 600): the fewest charms a weekly corpus snapshot may have before it's saved; a snapshot with fewer means clones failed.
5. Create the labels `agent`, `agent:plan-only`, `agent:running`, `agent:failed` and `needs design`.
6. Check that the branch rules for the default branch require a review that the bot can't give, so its PRs can't be merged without a maintainer, and add a ruleset for `agent/issue-*` that blocks force-pushes, so the bot can't rewrite a maintainer's commits on its own branches. (A revision already stops if its branch moved while the agent worked, so this is a second line of defence.) Canonical manages this repository's branch rules centrally rather than in its settings, so both are a change there.
7. Run the "Agent upkeep" workflow by hand once, to build the corpus.

The weekly upkeep workflow also opens an issue when either credential expires within 14 days or has stopped working, or when the key has less credit left than a week's spending. It opens the issue as `github-actions[bot]`, not as the bot, whose token may be the one that failed.
