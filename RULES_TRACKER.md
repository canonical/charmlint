# Rules refactor tracker

Goal: strip all rules except META001 to a clean reviewable core, then re-add
every rule via its own draft PR. **No rule lands without a PR.**

Each row below must reach a green `PR #` before this refactor is finished.

| Group | Rule IDs | Source module | Tests | PR | Status |
|---|---|---|---|---|---|
| (core kept) | META001 | `_rules/metadata.py` | `test_rules.py::TestMetadataRules`, `test_linter.py`, `test_properties.py` | — | kept |
| META 002-007 | META002, META003, META004, META005, META006, META007 | `_rules/metadata.py` | `test_rules.py::TestMetadataRules` | #95 | open |
| COS 001-004 | COS001, COS002, COS003, COS004 | `_rules/observability.py` (factory) | `test_rules.py::TestObservabilityRules` | | pending |
| COS005 | COS005 | `_rules/observability.py` | `test_rules.py::TestObservabilityRules` | | pending |
| STS 001-003 | STS001, STS002, STS003 | `_rules/status.py` (factory) | `test_rules.py::TestStatusRules` | | pending |
| DEP 001-004 | DEP001, DEP002, DEP003, DEP004 | `_rules/deprecated.py` (factory) | `test_rules.py::TestDeprecatedRules` | | pending |
| CC001 | CC001 | `_rules/charmcraft_compat.py` | `test_charmcraft_compat.py` | | pending |
| CC002 | CC002 | `_rules/charmcraft_compat.py` | `test_charmcraft_compat.py` | | pending |
| CC003 | CC003 | `_rules/charmcraft_compat.py` | `test_charmcraft_compat.py` | | pending |
| CC004 | CC004 | `_rules/charmcraft_compat.py` | `test_charmcraft_compat.py` | | pending |
| CC005/CC006 | CC005, CC006 | `_rules/unknown_fields.py` (shared known-field tables) | `test_unknown_fields.py` | | pending |
| ATT001 | ATT001 | `_rules/attestations.py` | `test_attestations.py` | | pending |
| ATT002 | ATT002 | `_rules/attestations.py` | `test_attestations.py` | | pending |
| PEB001 | PEB001 | `_rules/pebble.py` | `test_rules.py::TestPebbleRules` | | pending |
| PEB002 | PEB002 | `_rules/pebble.py` | `test_rules.py::TestPebbleRules` | | pending |
| PEB003 | PEB003 | `_rules/pebble.py` | `test_rules.py::TestPebbleRules` | | pending |
| ACT 001-003 | ACT001, ACT002, ACT003 | `_rules/actions.py` (factory, shared `_EXPECTED_ACTIONS`) | `test_rules.py::TestActionRules` | | pending |
| ACT004 | ACT004 | `_rules/actions.py` | `test_rules.py::TestActionRules` | | pending |
| ACT005 | ACT005 | `_rules/actions.py` | `test_rules.py::TestActionRules` | | pending |
| ACT006 | ACT006 | `_rules/actions.py` | `test_rules.py::TestActionRules` | | pending |
| ACT007 | ACT007 | `_rules/actions.py` | `test_rules.py::TestActionRules` | | pending |
| CFG001 | CFG001 | `_rules/config_quality.py` | `test_rules.py::TestConfigRules` | | pending |
| CFG002 | CFG002 | `_rules/config_quality.py` | `test_rules.py::TestConfigRules` | | pending |
| CFG003 | CFG003 | `_rules/config_quality.py` | `test_rules.py::TestConfigRules` | | pending |
| CFG004 | CFG004 | `_rules/config_quality.py` | `test_rules.py::TestConfigRules` | | pending |
| CFG005 | CFG005 | `_rules/config_quality.py` | `test_rules.py::TestConfigRules` | | pending |
| DOC001 | DOC001 | `_rules/documentation.py` | `test_rules.py::TestDocumentationRules` | | pending |
| DOC002 | DOC002 | `_rules/documentation.py` | `test_rules.py::TestDocumentationRules` | | pending |
| DOC003 | DOC003 | `_rules/documentation.py` | `test_rules.py::TestDocumentationRules` | | pending |
| DOC004 | DOC004 | `_rules/documentation.py` | `test_rules.py::TestDocumentationRules` | | pending |
| DOC005 | DOC005 | `_rules/documentation.py` | `test_rules.py::TestDocumentationRules` | | pending |
| LIB001 | LIB001 | `_rules/libraries.py` | `test_rules.py::TestLibraryRules` | | pending |
| LIB002 | LIB002 | `_rules/libraries.py` | `test_rules.py::TestLibraryRules` | | pending |
| LIB003/LIB004 | LIB003, LIB004 | `_rules/library_versions.py` (shared parser) | `test_rules.py::TestLibraryVersions` | | pending |
| REL001 | REL001 | `_rules/relation_data.py` | `test_rules.py::TestRelationDataRules` | | pending |
| REL002 | REL002 | `_rules/relation_data.py` | `test_rules.py::TestRelationDataRules` | | pending |
| SEC001 | SEC001 | `_rules/security.py` | `test_rules.py::TestSecurityRules` | | pending |
| SEC002 | SEC002 | `_rules/security.py` | `test_rules.py::TestSecurityRules` | | pending |
| STR001 | STR001 | `_rules/structure.py` | `test_rules.py::TestStructureRules` | | pending |
| STR002 | STR002 | `_rules/structure.py` | `test_rules.py::TestStructureRules` | | pending |
| STR003 | STR003 | `_rules/structure.py` | `test_rules.py::TestStructureRules` | | pending |
| TEST001 | TEST001 | `_rules/testing.py` | `test_rules.py::TestTestingRules` | | pending |
| TEST002 | TEST002 | `_rules/testing.py` | `test_rules.py::TestTestingRules` | | pending |
| TEST003 | TEST003 | `_rules/testing.py` | `test_rules.py::TestTestingRules` | | pending |

## Counts

- 61 rule IDs total across 17 modules
- 1 kept in core (META001)
- 60 to re-land via 43 PRs (factory-shared groups collapsed: META 6→1, COS 4→1, STS 3→1, DEP 4→1, ACT001-003 3→1, CC005/006 2→1, LIB003/004 2→1)

## Process

1. Strip PR (this branch) lands first.
2. Every add-back branch is cut from `refactor/strip-rules`; once strip lands on `main`, GitHub auto-rebases the diffs.
3. Each add-back PR restores: rule code (or factory entry), tests, `_rules/__init__.py` import if a whole module returns, and any `docs/` references.
4. Locally verify each with `make test && make lint` before pushing; CI runs the same checks plus the test matrix on each PR.
