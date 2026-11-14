Correctness and edge cases:

- Does the rule flag exactly what its docstring says, and pass over what it
  says it passes over? Look for inputs the tests don't cover: missing keys,
  wrong types, empty files, `config.yaml` vs `charmcraft.yaml`, monorepos,
  keyword vs positional arguments, aliases and `from x import y` forms.
- String prefixes and paths: matching `startswith("ops")` also matches
  `opsx`; match whole components, not substrings.
- Lookups that keep one value (`dict[k] = v`, return on first match): can
  there be several?
- Report every independent problem, not only the first.
- Fail loudly: every `except ...: pass`, `contextlib.suppress`, `or {}`
  fallback or silent skip needs a reason; a file that is present but broken
  is never reported as missing.
- Rule code only parses: no `eval`, `exec`, `subprocess`, `importlib`, or
  network access, and nothing from the charm is executed.
- Do the corpus FPs (if any) point at a pattern the rule should exclude?
- Recall: read the "Not flagged" list in the corpus results. A real
  instance of the problem labelled `DEFERRED` (or wrongly `OK`) that this
  change could cover with the existing helpers is blocking; a deferral is
  only fine when it needs the linter core or another open issue covers it.
