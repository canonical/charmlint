You are re-reviewing a pull request to charmlint after the author responded
to an earlier review. You are in the repository with the change applied.
Read `AGENTS.md` first.

- The earlier review's blocking findings, numbered: `{previous}`.
- The author's response: `{response}`.
- What changed since that review (the fix only): `{fix_diff}`.
- The whole change against main, for context: `{diff}`.

This is a scoped re-review, not a fresh one:

1. For each earlier finding, decide whether it is now resolved. Open the
   code to check; don't take the response's word for it. If the author
   disputed a finding instead of changing the code, decide whether their
   reason holds.
2. Then look only at the fix diff, and report problems the fix itself
   introduced. Don't raise anything about code the fix didn't touch: that
   was the earlier review's job.

Don't edit any file. Write `{out}`: a JSON object, exactly:

{{"previous": [{{"index": <int>, "status": "resolved|not_resolved|dispute_accepted|dispute_rejected", "note": "<one sentence>"}}], "findings": [{{"severity": "blocking|should|nit", "file": "<path>", "line": <int or null>, "problem": "<what the fix broke>", "fix": "<what to do instead>"}}], "summary": "<one sentence>"}}
