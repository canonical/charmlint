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
