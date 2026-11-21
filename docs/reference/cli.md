---
myst:
  html_meta:
    description: Reference for the charmlint command-line interface, including its options and exit codes.
---

# Command-line interface

```{eval-rst}
.. autoprogram:: charmlint._cli:_build_parser()
   :prog: charmlint
```

## Exit codes

| Code | Meaning |
|---|---|
| 0 | No errors were found. With `--strict`, no errors or warnings were found. |
| 1 | At least one error was found. |
| 2 | With `--strict`, at least one warning and no errors were found. Also used when charmlint can't run: the path isn't a directory, the configuration is invalid, a rule named in `select` or `ignore` doesn't exist, or the command-line options are invalid. |

Findings at the `info` severity never change the exit code.
