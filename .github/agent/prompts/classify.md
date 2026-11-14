You are checking a charmlint rule's findings over a corpus of real charms.
Each finding is either right or wrong, and your job is to decide which,
independently of whoever wrote the rule.

What the rule is meant to do (its plan and docstring) is in `{rule_doc}`.
The findings are in `{findings}`, one JSON object per line, with `id`,
`charm`, `path`, `line`, `rule_id`, `message`, `change` (`added` or
`removed` relative to main) and `snippet` (the lines around the finding,
with the flagged line marked `>>`). The corpus is at `{corpus}` if you need
more context than the snippet: open the file under `{corpus}/<charm>/<path>`.

For each finding, decide:

- `TP` - the rule is right, and the charm author would want to know.
- `EXPECTED` - the rule is technically right, but this is a deliberate
  choice the author would suppress (say why).
- `FP` - the rule is wrong: the code doesn't have the problem, or the rule
  misread it (say exactly what it misread).
- `UNK` - you can't tell, even after opening the file.

Work in two passes. First read all the findings and group them into a
small number of patterns (usually two to six): the kinds of code the rule
fires on, named the way a maintainer would describe them in a PR ("periodic
job written as a check", "readiness check at the alive level"). Then label
each finding, using one of those pattern names, so that findings of the
same pattern get the same label unless the code of one shows something the
others don't.

`EXPECTED` needs evidence in the code that the author chose this on
purpose and would keep it: a comment saying so, a name or docstring that
says what it's for, or it mirroring something upstream does deliberately.
That the code *could* be intentional isn't enough; without evidence, it's
`TP`. The issue (in the plan) may describe the expected cases; use that
description where it fits.

For a `removed` finding (a changed rule no longer reports something), the
question is whether removing it was right: `TP` means "correctly no longer
reported", `FP` means "a real problem is now missed".

Write `{out}`: one JSON object per line, one for every finding, in the same
order, exactly:

{{"id": <id>, "label": "TP|EXPECTED|FP|UNK", "reason": "<one sentence>", "pattern": "<a 2-6 word name for the kind of case>"}}

Judge each finding against *why* the problem matters - the reason the
issue gives - not against what the rule was designed to match. A finding
that matches the rule's design exactly is still `FP` if that reason doesn't
hold in this charm. For example, if the problem is that an event never
fires again, a handler that is also observed for a repeating event doesn't
have the problem. Open the file and check the surrounding code before
deciding.

Keep that judgement to the flagged code and what it is wired to (the
function, the events it is observed for, the call it is part of). Don't
mark a finding `FP` because some other part of the charm might later undo
or work around the problem, such as another handler that resets a status:
a rule can't check that reliably, and the maintainer wants to hear about
it anyway. Where the issue says how to detect the problem, a finding that
matches that description is `TP` unless the flagged code itself defeats
the reason.

Judge from the code, not from the rule's message. Don't edit any other file.
