# 0.3.0 - 13 October 2026

## Features

* Add CORRECTNESS-009 (container-name-mismatch) ([#207](https://github.com/canonical/charmlint/pull/207))
* Add SUPPLYCHAIN-001 (oci-image-missing-upstream-source) ([#58](https://github.com/canonical/charmlint/pull/58))
* Add CONFIG-008 (config-options-not-nested) ([#411](https://github.com/canonical/charmlint/pull/411))
* Add STRUCTURE-003 (no-type-annotations) ([#140](https://github.com/canonical/charmlint/pull/140))
* Add FEATURES-007 (no-config-changed-observer) ([#54](https://github.com/canonical/charmlint/pull/54))
* Add a dev workshop ([#434](https://github.com/canonical/charmlint/pull/434))
* Add CONFIG-007 (config-default-type-mismatch) ([#406](https://github.com/canonical/charmlint/pull/406))

## Fixes

* Flag `bases`/`platforms` in metadata.yaml as misplaced ([#248](https://github.com/canonical/charmlint/pull/248))
* Don't print compile warnings about the charm's own code ([#343](https://github.com/canonical/charmlint/pull/343))
* Keep the reference URL when a severity override applies ([#339](https://github.com/canonical/charmlint/pull/339))
* Merge the duplicate [tool.ruff.format] tables ([#414](https://github.com/canonical/charmlint/pull/414))
* Apply an own-line directive to a line with its own trailing directive ([#403](https://github.com/canonical/charmlint/pull/403))

## Documentation

* Add a generated reference page for the rules ([#329](https://github.com/canonical/charmlint/pull/329))
* Regenerate the rule reference for SUPPLYCHAIN-001 ([#338](https://github.com/canonical/charmlint/pull/338))
* Correct the comment on naming an empty category ([#341](https://github.com/canonical/charmlint/pull/341))
* Refresh the README ([#405](https://github.com/canonical/charmlint/pull/405))
* Stop RST roles leaking into the rule reference ([#389](https://github.com/canonical/charmlint/pull/389))

## Tests

* Stop tests passing only because their input is FATAL ([#373](https://github.com/canonical/charmlint/pull/373))
* Deselect the reference-URL checks by default ([#391](https://github.com/canonical/charmlint/pull/391))

## CI

* Close the remaining Charm Tech baseline gaps ([#332](https://github.com/canonical/charmlint/pull/332))
* Stop Dependabot putting a scope in PR titles ([#415](https://github.com/canonical/charmlint/pull/415))
* The SBOM lists only charmlint's runtime dependencies ([#407](https://github.com/canonical/charmlint/pull/407))

# 0.2.1 - 23 September 2026

The same as 0.2.0, with the version number bumped.

# 0.2.0 - 23 September 2026

## Features

* Add CHARMCRAFT-007 (legacy-bases) ([#209](https://github.com/canonical/charmlint/pull/209))
* Add CONFIG-006 (config-option-undeclared) ([#208](https://github.com/canonical/charmlint/pull/208))
* Add TESTING-003 (uses-harness) ([#143](https://github.com/canonical/charmlint/pull/143))
* Add STATUS-001 (blocked-status-in-non-repeating-handler) ([#190](https://github.com/canonical/charmlint/pull/190))
* Add CHARMCRAFT-008/009 (charm-user, container user IDs) ([#241](https://github.com/canonical/charmlint/pull/241))
* Add CORRECTNESS-004 (non-deferrable-event-deferred) ([#21](https://github.com/canonical/charmlint/pull/21))
* Add CORRECTNESS-003: `container.exec()` result not consumed ([#40](https://github.com/canonical/charmlint/pull/40))
* Add CORRECTNESS-008 (observe-target-mismatch) ([#250](https://github.com/canonical/charmlint/pull/250))
* Adopt ruff's suppression-comment and rule-name style ([#255](https://github.com/canonical/charmlint/pull/255))
* Add SUPPLYCHAIN-005 and SUPPLYCHAIN-006: ops dependency pinning ([#67](https://github.com/canonical/charmlint/pull/67))
* Add FEATURES-004 (no-assumes-juju-version) ([#22](https://github.com/canonical/charmlint/pull/22))
* Add FEATURES-005 and FEATURES-006 (workload version) ([#46](https://github.com/canonical/charmlint/pull/46))
* Add CORRECTNESS-00{1,2} `event.defer()` not followed by return ([#38](https://github.com/canonical/charmlint/pull/38))

## Fixes

* A directory named test_*.py is not a Python file ([#211](https://github.com/canonical/charmlint/pull/211))
* Lint every charm in a multi-charm repository ([#240](https://github.com/canonical/charmlint/pull/240))

## Documentation

* Rewrite RULES_TRACKER to cover all open work, ordered by value
* Record the Phase 0 PRs in the tracker
* Track the rules that need type information in the tracker ([#262](https://github.com/canonical/charmlint/pull/262))
* Document how to measure a rule against the hyrum cache ([#264](https://github.com/canonical/charmlint/pull/264))
* Refresh the work tracker ([#268](https://github.com/canonical/charmlint/pull/268))

## Performance

* Only import importlib.metadata when --version is used ([#257](https://github.com/canonical/charmlint/pull/257))

# 0.1.1 - 2 September 2026

The same as 0.1.0, with the version number bumped.

# 0.1.0 - 2 September 2026

## Features

* Load config from pyproject.toml ruff-style ([#85](https://github.com/canonical/charmlint/pull/85))
* Add DOCUMENTATION-001 (no-readme) ([#123](https://github.com/canonical/charmlint/pull/123))
* Add CHARMCRAFT-001 (deprecated-series) ([#106](https://github.com/canonical/charmlint/pull/106))
* Add METADATA-002 through METADATA-007 ([#95](https://github.com/canonical/charmlint/pull/95))
* Add TEST001 (no-unit-tests) ([#141](https://github.com/canonical/charmlint/pull/141))
* Add STRUCTURE-001 (no-licence) ([#138](https://github.com/canonical/charmlint/pull/138))
* Add CHARMCRAFT-002 (naming-conventions) ([#107](https://github.com/canonical/charmlint/pull/107))
* Add SECURITY-001 (secret-in-plain-config) ([#136](https://github.com/canonical/charmlint/pull/136))
* Add LIBRARY-001 (fetch-libs-has-pypi) ([#130](https://github.com/canonical/charmlint/pull/130))
* Add ACTIONS-001 (action-missing-observer) ([#104](https://github.com/canonical/charmlint/pull/104))
* Add CHARMCRAFT-004, CHARMCRAFT-005 (unknown-field detection) ([#110](https://github.com/canonical/charmlint/pull/110))
* Add METADATA-00{8,9}: requires endpoint missing optional field ([#49](https://github.com/canonical/charmlint/pull/49))
* Add STRUCTURE-002 (no-icon) ([#139](https://github.com/canonical/charmlint/pull/139))
* Add CONFIG-001..003 (config type, default, description) ([#180](https://github.com/canonical/charmlint/pull/180))
* Add ACTIONS-002 (action-missing-additional-properties) ([#189](https://github.com/canonical/charmlint/pull/189))
* Add PEBBLE-005 (pebble-env-non-string) ([#194](https://github.com/canonical/charmlint/pull/194))
* Add METADATA-010 (circular-website-link) ([#188](https://github.com/canonical/charmlint/pull/188))
* Add ACTIONS-003/ACTIONS-004 (action and param descriptions) ([#182](https://github.com/canonical/charmlint/pull/182))
* Publish to PyPI on tag via Trusted Publishing ([#199](https://github.com/canonical/charmlint/pull/199))
* Add CHARMCRAFT-003 (entrypoint-issues) ([#108](https://github.com/canonical/charmlint/pull/108))
* Add CHARMCRAFT-006 (no-ops-main-call) ([#109](https://github.com/canonical/charmlint/pull/109))

## Fixes

* Fix false-positive regex and add missing path in diagnostic ([#90](https://github.com/canonical/charmlint/pull/90))
* Track metadata source file to fix wrong paths in CC005/META001-007 diagnostics ([#89](https://github.com/canonical/charmlint/pull/89))
* Use word-boundary matching to eliminate false positives ([#80](https://github.com/canonical/charmlint/pull/80))
* Stop walking ancestor docs/ directories in monorepos ([#81](https://github.com/canonical/charmlint/pull/81))
* Only flag when condition is present but no status call ([#82](https://github.com/canonical/charmlint/pull/82))
* Separate known-field sets for charmcraft.yaml vs metadata.yaml ([#91](https://github.com/canonical/charmlint/pull/91))
* Merge metadata.yaml into charmcraft.yaml when both files exist ([#24](https://github.com/canonical/charmlint/pull/24))
* Detect dynamic config access patterns to reduce false positives ([#57](https://github.com/canonical/charmlint/pull/57))

## Documentation

* Justify eager loading of Python sources
* Add rule ID scheme reference ([#34](https://github.com/canonical/charmlint/pull/34))
* Prep for a move to canonical
* Consolidate rule ID catalogue into docs/id-scheme.md ([#145](https://github.com/canonical/charmlint/pull/145))
* Add ruff-style versioning policy ([#178](https://github.com/canonical/charmlint/pull/178))
* Note that the project is early and where review should focus ([#196](https://github.com/canonical/charmlint/pull/196))

## Tests

* Add regression test for maintainers flagged in charmcraft.yaml ([#92](https://github.com/canonical/charmlint/pull/92))

## Refactoring

* General tidy-up
* Collapse pypi_attest into `charmlint._pypi_attest` ([#84](https://github.com/canonical/charmlint/pull/84))
* Strip all rules except META001 (clean-core review) ([#94](https://github.com/canonical/charmlint/pull/94))
* Various improvements for the baseline ([#147](https://github.com/canonical/charmlint/pull/147))
* Move requires/provides optional rules to METADATA ([#187](https://github.com/canonical/charmlint/pull/187))
* Carry file and line on YAML values ([#193](https://github.com/canonical/charmlint/pull/193))
* Parse Python sources once and share the AST matchers ([#197](https://github.com/canonical/charmlint/pull/197))
* Prefix internal modules with underscore ([#83](https://github.com/canonical/charmlint/pull/83))
* Flatten `_pypi_attest` package into a module

## Performance

* Use libyaml C loader when available ([#88](https://github.com/canonical/charmlint/pull/88))

## Uncategorised

* Fix cantrip charmlint issues and port missing rules to Rust ([#3](https://github.com/canonical/charmlint/pull/3))
