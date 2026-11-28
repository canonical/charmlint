# Rule ID scheme

charmlint rule IDs follow the form `CATEGORY-###`, such as `SECURITY-001` and `METADATA-003`. The category groups related rules, and the three-digit number is unique within that category.

## Principles

**Keep per-category prefixes.** Rules are not collapsed into a flat namespace. The category name makes triage faster: `PERFORMANCE-001` in CI output immediately signals a performance issue.

**Use full-word categories in uppercase.** Full words are unambiguous and split cleanly into `CATEGORY` and `###` with `id.rsplit("-", 1)`. This also makes charmlint IDs visually distinct from ruff's `PREFIX###` format, so there is no confusion about which tool reported `SEC001` versus `SECURITY-001`.

**Always use the full `CATEGORY-###` form.** Numbers are only unique within a category, so a bare `001` could mean any of several rules. charmlint rejects it in the configuration and on the command line, such as in `ignore = ["001"]` or `--ignore 001`.

## Category catalogue

| Category | Scope |
|---|---|
| METADATA | Metadata completeness |
| DOCUMENTATION | Documentation |
| OBSERVABILITY | Observability (COS stack) |
| SECURITY | Security |
| ATTESTATION | Supply chain attestations |
| TESTING | Testing quality |
| PEBBLE | Pebble |
| RELATIONS | Relation data |
| STATUS | Status reporting |
| CONFIG | Config quality |
| STRUCTURE | Structure |
| DEPRECATION | Deprecated APIs |
| LIBRARY | Library management |
| CHARMCRAFT | Charmcraft compatibility |
| ACTIONS | Actions |
| CORRECTNESS | Correctness |
| PERFORMANCE | Performance |
| FEATURES | Expected features |
| JUJU | Juju-ness / idiomatic ops |
| SUPPLYCHAIN | Supply chain / maintainability |
| OPS | Operational readiness |
| EVENTS | Event lifecycle completeness |

The catalogue is mirrored in code as `charmlint._rules.CATEGORIES`. A rule may only declare a category from that list, and configuration may only name one from it, so a typo in either is reported rather than silently matching nothing. Adding a category means adding it in both places.

## Rule names

Every rule also has a `name`: a kebab-case phrase saying what it checks, such as `secret-in-plain-config` for `SECURITY-001`. Names are ruff's wordier spelling, and charmlint accepts them anywhere an ID is accepted: `select`, `ignore`, `per-rule-severity`, `--select`, `--ignore`, and the codes inside a suppression comment.

A name must be unique across rules, must be kebab-case, and must not spell a category, because `ignore = ["security"]` would otherwise mean two different things. All three are enforced when the rule class is registered.

Names are part of the public interface, so renaming one is a breaking change under the [versioning policy](../explanation/versioning.md), the same as renumbering an ID.
