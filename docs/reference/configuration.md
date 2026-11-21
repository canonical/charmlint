# Configuration

Configure under `[tool.charmlint]` in `pyproject.toml`, or in a standalone `charmlint.toml` / `.charmlint.toml`. Discovery walks up from the charm directory.

```toml
[tool.charmlint]
severity = "warning"  # minimum severity to report
select = ["SECURITY", "METADATA"]
ignore = ["METADATA-002"]

[tool.charmlint.per-rule-severity]
"SECURITY-001" = "error"
```

In a standalone file, drop the `tool.charmlint` prefix: the keys sit at the top level, and the table is `[per-rule-severity]`.

`select`, `ignore`, the keys of `per-rule-severity`, and `--select` / `--ignore` accept these rule spellings:

| Spelling | Example | Means |
|---|---|---|
| Rule ID | `SECURITY-001` | that one rule |
| Rule name | `secret-in-plain-config` | that one rule |
| Category | `SECURITY` | every rule in the category |

A config can mix rule IDs and rule names.

Case is significant. Rule IDs and categories are upper-case, rule names lower-case; `security-001` names nothing.

When `select` and `ignore` disagree, the more specific spelling wins: `select = ["secret-in-plain-config"]` with `ignore = ["SECURITY"]` runs that one rule and no other security rule.

## Suppressing findings inline

Individual findings can be silenced from within a charm's YAML and Python files, with ruff-style suppression comments. Codes inside a directive are the same three spellings as `select` and `ignore` accept — rule ID, rule name, or category.

`# charmlint: ignore[...]` suppresses the listed rules on one line. At the end of a line it covers that line; on a line of its own it covers the next line that is not blank or a comment:

```yaml
config:
  options:
    admin-password:  # charmlint: ignore[SECURITY-001]
      type: string
    # charmlint: ignore[secret-in-plain-config]  # set by the operator
    api-token:
      type: string
```

On a line of its own, the directive must come first; put any explanation after it.

`# charmlint: file-ignore[...]`, wherever it appears, suppresses the listed rules across the whole file:

```python
# charmlint: file-ignore[CORRECTNESS-001]
```

Findings that anchor to a whole file rather than a line — a missing metadata field, say — can only be silenced by a file-level directive.

### Suppressing everything

`# charmlint: ignore` suppresses every finding on the line it governs, and `# charmlint: file-ignore` every finding in the file:

```yaml
# charmlint: file-ignore
config:
  options:
    admin-password:  # charmlint: ignore
      type: string
```

`ignore` never reaches beyond the one line it governs. To silence a whole file, use `file-ignore`.

### The bare `# noqa` form

In YAML, an inline `# noqa` suppresses every finding on that line, and `# noqa: SECURITY-001, METADATA-002` suppresses the listed rules:

```yaml
config:
  options:
    admin-password:  # noqa
      type: string
```

In Python files, charmlint only considers `# charmlint:` directives; `# noqa` is for ruff.

