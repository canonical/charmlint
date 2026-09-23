# Configuration

Configure under `[tool.charmlint]` in `pyproject.toml`, or in a standalone
`charmlint.toml` / `.charmlint.toml`. Discovery walks up from the charm
directory, in the manner of ruff.

```toml
[tool.charmlint]
severity = "warning"  # minimum severity to report
select = ["SECURITY", "METADATA"]
ignore = ["METADATA-002"]

[tool.charmlint.per-rule-severity]
"SECURITY-001" = "error"
```

Everywhere a rule is named — `select`, `ignore`, the keys of
`per-rule-severity`, and `--select` / `--ignore` on the command line — it
can be spelled three ways:

| Spelling | Example | Means |
|---|---|---|
| Rule ID | `SECURITY-001` | that one rule |
| Rule name | `secret-in-plain-config` | that one rule |
| Category | `SECURITY` | every rule in the category |

Names are the wordier spelling, in the manner of ruff: `ignore =
["secret-in-plain-config"]` says what has been turned off without a trip
to the rule catalogue. Both spellings resolve to the same rule, so a
config can mix them.

A spelling that names nothing charmlint knows about is an error rather
than a rule that silently never fires, so a typo is caught at startup.
Only rules that exist in the running charmlint count as known: a
category with no rules yet, and a well-formed ID for a rule that has not
landed (`OBSERVABILITY-005`), are both rejected.

Case is significant. Rule IDs and categories are upper-case, rule names
lower-case; `security-001` names nothing.

When `select` and `ignore` disagree, the more specific spelling wins:
`select = ["secret-in-plain-config"]` with `ignore = ["SECURITY"]` runs
that one rule and no other security rule.

## Suppressing findings inline

Individual findings can be silenced from within a charm's YAML and Python
files, with ruff-style suppression comments. Codes inside a directive are
the same three spellings as `select` and `ignore` accept — rule ID, rule
name, or category.

`# charmlint: ignore[...]` suppresses the listed rules on one line. At the
end of a line it covers that line; on a line of its own it covers the next
line that is not blank or a comment, so a directive can sit above the
thing it excuses:

```yaml
config:
  options:
    admin-password:  # charmlint: ignore[SECURITY-001]
      type: string
    # charmlint: ignore[secret-in-plain-config]  # set by the operator
    api-token:
      type: string
```

A directive on its own line must start that line: free text belongs
after it, not before, or the directive is read as trailing the comment
line itself.

`# charmlint: file-ignore[...]`, wherever it appears, suppresses the
listed rules across the whole file:

```python
# charmlint: file-ignore[CORRECTNESS-001]
```

Findings that anchor to a whole file rather than a line — a missing
metadata field, say — can only be silenced by a file-level directive.

### Suppressing everything

The code list is optional on both verbs. `# charmlint: ignore` suppresses
every finding on the line it governs, and `# charmlint: file-ignore`
every finding in the file:

```yaml
# charmlint: file-ignore
config:
  options:
    admin-password:  # charmlint: ignore
      type: string
```

Scope is decided by the verb and by where the directive is written, and
by nothing else: no directive silences a whole file from the end of a
line of config. To silence a file, write `file-ignore` on a line of its
own.

### The bare `# noqa` form

In YAML, charmlint also honours the bare form it has always accepted: an
inline `# noqa` suppresses every finding on that line, and `# noqa:
SECURITY-001, METADATA-002` suppresses the listed rules.

```yaml
config:
  options:
    admin-password:  # noqa
      type: string
```

It is not honoured in Python files: there, `# noqa` is ruff's, and
charmlint neither consumes ruff's directives nor asks a charm to write
one that ruff would then report as unused. Python files take the
`# charmlint:` forms only.

