Tests and house conventions:

- Prove it: would each positive test still pass if the rule's main condition
  were removed? A test that passes either way is blocking.
- Positive and negative cases for every bullet in the docstring, in the
  style of the neighbouring tests.
- Module layout (AGENTS.md): rule classes first in ID order, helpers below
  their first caller in call order. Shared concerns in `_ast.py` / `_yaml.py`,
  not a new private walker that duplicates one there.
- Parse once: use the charm context and shared models rather than
  re-reading and re-validating raw YAML in the rule.
- The docstring is user documentation rendered into `docs/rules.md`: what it
  flags, why it matters, what it passes over. No design rationale, no reST
  roles, no internal names a user wouldn't know.
- Rule ID `CATEGORY-NNN`, next free number in a category that fits the
  subject; kebab-case name; severity justified.
- `reference_url` is a real stable docs page that covers the problem.
- No comments that restate the code; no unnecessary defensive code.
- Only files under `src/charmlint/_rules/`, `_ast.py`, `_yaml.py`, `tests/`
  and `docs/rules.md` changed.
