# Rule ID scheme

Charmlint rule IDs follow the form `PREFIX###`, for example `SEC001`,
`META003`. The prefix groups rules by lens; the three-digit numeric suffix
is unique within that prefix.

## Principles

**Keep per-lens prefixes.** Rules are not collapsed into a flat namespace.
The lens prefix makes triage faster: `PERF001` in CI output immediately
signals a performance issue.

**Standardise to 3–5 uppercase letters.** Existing prefixes are 2–5
characters. New prefixes (`CORR`, `PERF`, `FEAT`, `JUJU`, `SUPP`, `OPS`,
`EVNT`) fit naturally inside that range. Avoid single-letter prefixes —
they are ambiguous and read poorly in mixed CI output.

**Do not reuse numeric suffixes across lenses.** Numbers are per-lens, so a
ruleset config of `disable: ["001"]` would be ambiguous. The fully
qualified `PREFIX###` form is the only identifier; configuration must use
the full form.

## Prefix catalogue

| Prefix | Lens |
|---|---|
| META | Metadata completeness |
| DOC | Documentation |
| COS | Observability (COS stack) |
| SEC | Security |
| ATT | Supply chain attestations |
| TEST | Testing quality |
| PEB | Pebble |
| REL | Relation data |
| STS | Status reporting (see rename candidate below) |
| CFG | Config quality |
| STR | Structure |
| DEP | Deprecated APIs |
| LIB | Library management |
| CC | Charmcraft compatibility |
| ACT | Actions |
| CORR | Correctness |
| PERF | Performance |
| FEAT | Expected features |
| JUJU | Juju-ness / idiomatic ops |
| SUPP | Supply chain / maintainability |
| OPS | Operational readiness |
| EVNT | Event lifecycle completeness |

## Rename candidate: STS → STAT

`STS` (status) clashes visually with `STR` (structure) — both are three
letters, both start with `ST`, and in CI output they are easy to confuse.
A future breaking change should rename `STS` to `STAT`, keeping `STS` as
an alias for one release cycle.

This is tracked separately so the rename can happen at a coordinated
breaking-change boundary rather than piecemeal.
