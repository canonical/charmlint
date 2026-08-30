# Rules refactor tracker

Goal: strip all rules except META001 to a clean reviewable core, then re-add
every rule via its own draft PR. **No rule lands without a PR.**

Each row below must reach a green `PR #` before this refactor is finished.

| Group | Rule IDs | Source module | Tests | PR | Status |
|---|---|---|---|---|---|
| (core kept) | META001 | `_rules/metadata.py` | `test_rules.py::TestMetadataRules`, `test_linter.py`, `test_properties.py` | — | kept |
| METADATA 002-007 | METADATA-002, METADATA-003, METADATA-004, METADATA-005, METADATA-006, METADATA-007 | `_rules/metadata.py` | `test_rules.py::TestMetadataRules` | #95 | merged |
| COS 001-004 | COS001, COS002, COS003, COS004 | `_rules/observability.py` (factory) | `test_rules.py::TestObservabilityRules` | | pending |
| COS005 | COS005 | `_rules/observability.py` | `test_rules.py::TestObservabilityRules` | | pending |
| STS 001-003 | STS001, STS002, STS003 | `_rules/status.py` (factory) | `test_rules.py::TestStatusRules` | | pending |
| DEP 001-004 | DEP001, DEP002, DEP003, DEP004 | `_rules/deprecated.py` (factory) | `test_rules.py::TestDeprecatedRules` | | pending |
| CHARMCRAFT-001 | CHARMCRAFT-001 | `_rules/charmcraft_compat.py` | `test_charmcraft_compat.py` | #106 | merged |
| CHARMCRAFT-002 | CHARMCRAFT-002 | `_rules/charmcraft_compat.py` | `test_charmcraft_compat.py` | #107 | in review |
| CC003 | CC003 | `_rules/charmcraft_compat.py` | `test_charmcraft_compat.py` | | pending |
| CC004 | CC004 | `_rules/charmcraft_compat.py` | `test_charmcraft_compat.py` | | pending |
| CHARMCRAFT-004/005 | CHARMCRAFT-004, CHARMCRAFT-005 (were CC005/CC006 pre-renumber) | `_rules/charmcraft_compat.py` (shared known-field tables) | `test_charmcraft_compat.py` | #110 | in review |
| ATT001 | ATT001 | `_rules/attestations.py` | `test_attestations.py` | | pending |
| ATT002 | ATT002 | `_rules/attestations.py` | `test_attestations.py` | | pending |
| PEB001 | PEB001 | `_rules/pebble.py` | `test_rules.py::TestPebbleRules` | | pending |
| PEB002 | PEB002 | `_rules/pebble.py` | `test_rules.py::TestPebbleRules` | | pending |
| PEB003 | PEB003 | `_rules/pebble.py` | `test_rules.py::TestPebbleRules` | | pending |
| PEBBLE-005 | PEBBLE-005 (new, issue #155) | `_rules/pebble.py` | `test_pebble.py` | | in review |
| ACT 001-003 | ACT001, ACT002, ACT003 | `_rules/actions.py` (factory, shared `_EXPECTED_ACTIONS`) | `test_rules.py::TestActionRules` | | pending |
| ACTIONS-001 | ACTIONS-001 (was ACT006 pre-renumber) | `_rules/actions.py` | `test_actions.py` | #104 | merged |
| ACTIONS-003 | ACTIONS-003 (was ACT004 pre-renumber) | `_rules/actions.py` | `test_actions.py` | #182 | in review |
| ACTIONS-004 | ACTIONS-004 (was ACT005 pre-renumber) | `_rules/actions.py` | `test_actions.py` | #182 | in review |
| ACT007 | ACT007 | `_rules/actions.py` | `test_rules.py::TestActionRules` | | pending |
| CONFIG 001-003 | CONFIG-001, CONFIG-002, CONFIG-003 (were CFG001-CFG003 pre-renumber) | `_rules/config_quality.py` | `test_config_quality.py` | | in review |
| CFG004 | CFG004 | `_rules/config_quality.py` | `test_rules.py::TestConfigRules` | | pending |
| CFG005 | CFG005 | `_rules/config_quality.py` | `test_rules.py::TestConfigRules` | | pending |
| DOCUMENTATION-001 | DOCUMENTATION-001 | `_rules/documentation.py` | `test_rules.py::TestDocumentationRules` | #123 | merged |
| DOC002 | DOC002 | `_rules/documentation.py` | `test_rules.py::TestDocumentationRules` | | pending |
| DOC003 | DOC003 | `_rules/documentation.py` | `test_rules.py::TestDocumentationRules` | | pending |
| DOC004 | DOC004 | `_rules/documentation.py` | `test_rules.py::TestDocumentationRules` | | pending |
| DOC005 | DOC005 | `_rules/documentation.py` | `test_rules.py::TestDocumentationRules` | | pending |
| LIBRARY-001 | LIBRARY-001 | `_rules/libraries.py` | `test_rules.py::TestLibraryRules` | #130 | in review |
| LIB002 | LIB002 | `_rules/libraries.py` | `test_rules.py::TestLibraryRules` | | pending |
| LIB003/LIB004 | LIB003, LIB004 | `_rules/library_versions.py` (shared parser) | `test_rules.py::TestLibraryVersions` | | pending |
| REL001 | REL001 | `_rules/relation_data.py` | `test_rules.py::TestRelationDataRules` | | pending |
| REL002 | REL002 | `_rules/relation_data.py` | `test_rules.py::TestRelationDataRules` | | pending |
| SECURITY-001 | SECURITY-001 | `_rules/security.py` | `test_security.py` | #136 | in review |
| SEC002 | SEC002 | `_rules/security.py` | `test_security.py` | | pending |
| STR001 | STR001 | `_rules/structure.py` | `test_rules.py::TestStructureRules` | #138 | in review |
| STRUCTURE-002 | STRUCTURE-002 (was STR002 pre-renumber) | `_rules/structure.py` | `test_rules.py::TestStructureRules` | #139 | in review |
| STR003 | STR003 | `_rules/structure.py` | `test_rules.py::TestStructureRules` | | pending |
| TESTING-001 | TESTING-001 | `_rules/testing.py` | `test_rules.py::TestTestingRules` | | in review |
| TEST002 | TEST002 | `_rules/testing.py` | `test_rules.py::TestTestingRules` | | pending |
| TEST003 | TEST003 | `_rules/testing.py` | `test_rules.py::TestTestingRules` | | pending |
| METADATA 008/009 | METADATA-008, METADATA-009 | `_rules/metadata.py` (shared `_missing_optional_diagnostics`) | `test_metadata.py` | #49 | in review |
| METADATA-010 | METADATA-010 | `_rules/metadata.py` | `test_metadata.py` | #188 | in review |
| FEATURES-001 | FEATURES-001 (was FEAT001 pre-renumber) | `_rules/features.py` | `test_features.py` | #23 | in review |

## Counts

- 61 rule IDs total across 17 modules
- 1 kept in core (META001)
- 60 to re-land via 40 PRs (shared-module groups collapsed: META 6→1, COS 4→1, STS 3→1, DEP 4→1, ACT001-003 3→1, ACT004/005 2→1, CONFIG 001-003 3→1, CC005/006 2→1, LIB003/004 2→1)

## Process

1. Strip PR (this branch) lands first.
2. Every add-back branch is cut from `refactor/strip-rules`; once strip lands on `main`, GitHub auto-rebases the diffs.
3. Each add-back PR restores: rule code (or factory entry), tests, `_rules/__init__.py` import if a whole module returns, and any `docs/` references.
4. Locally verify each with `make test && make lint` before pushing; CI runs the same checks plus the test matrix on each PR.
