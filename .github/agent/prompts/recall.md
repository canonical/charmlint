You are checking a charmlint rule for misses: places in real charms that
have the problem the rule is about but that the rule doesn't flag.

What the rule is meant to do (its plan and the change) is in `{rule_doc}`.
The candidates are in `{hits}`, one JSON object per line, with `id`,
`charm`, `path`, `line`, `text` (the matching line) and `snippet` (the
lines around it, the matching line marked `>>`). They come from a broad
grep, and the rule flagged nothing near any of them. The corpus is at
`{corpus}` if you need more context: open `{corpus}/<charm>/<path>`.

For each candidate, decide:

- `MISSED` - this is a case the rule, as its plan and docstring describe
  it, should report, and it doesn't.
- `DEFERRED` - it is the problem, but the plan explicitly leaves this way
  of writing it for later. Say which part of the plan.
- `OK` - the rule is right not to report it: it isn't the problem (a
  query, a different setting, a comment, unrelated code that happens to
  match).
- `UNK` - you can't tell, even after opening the file.

Write `{out}`: one JSON object per line, one for every candidate, in the
same order, exactly:

{{"id": <id>, "label": "MISSED|DEFERRED|OK|UNK", "reason": "<one sentence>", "pattern": "<a 2-6 word name for the kind of case>"}}

Judge from the code. Don't edit any other file.
