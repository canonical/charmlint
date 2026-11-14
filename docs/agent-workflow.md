# The agent workflow

An agent turns approved issues into pull requests, and revises its own pull requests after review. It runs in GitHub Actions with open-weight models through OpenRouter. It opens PRs as `prints-charming-bot`, and a maintainer reviews and merges them like any other PR. The code is in `.github/agent/`, and the workflows are `.github/workflows/agent.yaml` and `.github/workflows/agent-weekly.yaml`.

## Using it

Label an issue `agent` to approve it. The agent plans the change, implements it, measures it over the charm corpus, reviews it, and opens a PR. The PR is a draft when a review finding or a possible miss is still open, and the PR body lists them.

Label an issue `agent:plan-only` to see the plan first. The agent posts the plan as a comment and stops. Edit the plan in that comment if it needs changing, then label the issue `agent` to implement it.

To revise a PR, submit a review that requests changes. The agent addresses the review comments, measures and reviews the change again, pushes a new commit and comments with what it did. It revises a PR at most three times. The review event itself only starts a run of the workflow on the default branch, so a revision runs with the same credentials and checks as a new PR.

Only labels and reviews from users in the `AGENT_ALLOWLIST` variable count. If someone else edits the issue after it's labelled, the agent doesn't run, and comments to say so.

At most `AGENT_MAX_OPEN_PRS` agent PRs are open at a time. An issue labelled while that many are open waits. A scheduled run twice a day picks up the oldest waiting issue.

The workflow can also be run by hand, with an issue number, from the Actions tab.

When a run fails, the agent comments on the issue with a link to the run, removes `agent` and adds `agent:failed`. Every stage's prompt, transcript and output is kept as an artefact of the run for 90 days.

## How it runs

The workflow has three jobs.

| Job | Credentials | What it does |
|---|---|---|
| triage | read-only token, plus adding `agent:running` | Checks who applied the label and whether the issue changed since, and snapshots the issue. No model. |
| agent | the OpenRouter key, held by a proxy | Runs the pipeline. No GitHub write access. |
| publish | the bot's token | Checks the patch, commits it as the bot, pushes `agent/issue-N` and opens the PR. No model. |

The pipeline and every tool the models use run as an `agent` user. That user has no `sudo`, can't see other users' processes or read the runner's home directory, and gets none of the job's tokens. Once its Python environments are installed, it can only reach the key proxy on localhost.

The OpenRouter key is held by a proxy that runs as a third user and reads the key from standard input. The proxy only forwards the configured models, pinned to their first-party providers. It refuses requests once the run has spent one and a half times `AGENT_BUDGET_USD`.

Because the agent could write any of the agent job's output, the publish job checks all of it. It builds on the commit triage recorded, not one the agent names. It applies the patch and then checks the result: only the rule code, tests, `docs/rules.md` and `RULES_TRACKER.md` may change, only as ordinary files, and rule code may not import modules such as `subprocess` or call `eval`. It writes the commit message itself. From the PR text it removes links to unexpected sites, anything shaped like a secret, @-mentions and closing keywords, and then adds `Fixes #N` itself. Plans are posted inside a fenced block, so what a maintainer reads on the issue is exactly what a later run uses.

| Item | Answer |
|---|---|
| Trigger | An allowlisted maintainer's `agent` or `agent:plan-only` label, the scheduled drain, a changes-requested review from an allowlisted reviewer, or a manual run |
| Permissions | Agent job: `contents: read` and the OpenRouter key through a proxy. Publish job: the bot's token, scoped to this repository |
| Data boundary | Public only: charmlint, its public issues, and the public charm corpus |
| Models | GLM 5.3 and Kimi K2.7 through OpenRouter, pinned to their first-party providers |
| Spending limit | The OpenRouter key's credit limit, and `AGENT_BUDGET_USD` per run (default $6), enforced by the key proxy |
| Timeout | `timeout-minutes` on each job, and bounded fix rounds in the pipeline |
| Failure behaviour | A comment on the issue with the run link, and the `agent:failed` label. Nothing else is blocked |
| Audit trail | The Actions log, every stage's outputs as artefacts, and a link to the run in each PR |
| Human approval | A label before any work, and a maintainer's review and merge after |

## The corpus

The agent measures every rule over the same charm corpus that [corpus.md](corpus.md) describes. A weekly workflow clones the charms in hyrum's charm list, drops build output and large files, and stores the result in the Actions cache. The agent job uses the newest copy.

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
   - `AGENT_MAX_OPEN_PRS` (optional, default 2), `AGENT_BUDGET_USD` (optional, default 6) and `AGENT_MODELS` (optional, the OpenRouter models the proxy forwards, separated by commas).
5. Create the labels `agent`, `agent:plan-only`, `agent:running` and `agent:failed`.
6. Check that the branch rules for the default branch require a review that the bot can't give, so its PRs can't be merged without a maintainer.
7. Run the "Agent upkeep" workflow by hand once, to build the corpus.

The weekly upkeep workflow also opens an issue when either credential expires within 14 days, or when the key has less credit left than a week's spending.
