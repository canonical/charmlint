# charmlint work tracker

This tracks **all** outstanding charmlint work, not just the rules
refactor: the rules that are still to be restored from the strip, the
new rules that have been proposed since, the engine work they depend
on, and the bugs in rules that already ship.

As of 2026-09-21 there are 14 open PRs and 133 open issues. The issue
queue is longer than the team can review in the order it was opened, so
the sections below are ordered by expected value rather than by number.

## Where we are

44 rules are registered, across 14 modules:

| Category | Landed |
|---|---|
| ACTIONS | 001, 002, 003, 004 |
| CHARMCRAFT | 001–009 |
| CONFIG | 001, 002, 003, 006 |
| CORRECTNESS | 001, 002, 003, 004, 008 |
| DOCUMENTATION | 001 |
| FEATURES | 004 |
| LIBRARY | 001 |
| METADATA | 001–010 |
| PEBBLE | 005 |
| SECURITY | 001 |
| STATUS | 001 |
| STRUCTURE | 001, 002 |
| SUPPLYCHAIN | 005, 006 |
| TESTING | 001, 003 |

The strip-and-re-add refactor (#94) is half done: of the 61 pre-strip
rule IDs, 31 are back, and the rest are listed in the restoration
ledger below. The other thirteen registered rules are new since the
strip. Every rule still lands via its own PR.

## How this list is ordered

Value is `charms affected × severity of the defect ÷ false-positive
risk`, with two things jumping the queue:

1. **False positives in rules that already ship.** CONTRIBUTING.md
   says a false positive is worse than a gap, and a rule that is
   already in the default `select` is costing trust today.
2. **Engine work several queued rules are blocked on.** Anything that
   is otherwise re-implemented per rule, or that would have to be
   retrofitted into every rule written before it.

Counts come from two corpora and are quoted from the issue that
records them: the charm-review corpus (136–149 charms deployed and
read one at a time) and the hyrum charm cache (~550–1026 charm
directories). Both count *charms where the defect exists*, not charms
the rule would fire on, so they are an upper bound on recall — see
#239 for the caveats, and for the decision still owed on whether the
count lives here or as an issue label.

## Phase 0 — Bugs in shipped rules

Nothing else should be reviewed ahead of these. All four PRs are
open and awaiting review.

| Issue | PR | Rule | Problem |
|---|---|---|---|
| #243 | #245 | CHARMCRAFT-003 | `exec` in a `dispatch` comment is parsed as the entrypoint and reported as an error |
| #244 | #246 | ACTIONS-001 | Fires once per action on a charm with no Python sources at all |
| #198 | #247 | LIBRARY-001 | Flags the charm's own published library, telling it to delete its own source |
| #210 | #248 | CHARMCRAFT-004 | `bases`/`platforms` in `metadata.yaml` are treated as valid; fell out of the #209 corpus run |

## Phase 1 — Engine work

| Issue | PR | Work | Why now |
|---|---|---|---|
| #181 | | Isolate rule crashes into a diagnostic | One rule raising aborts the whole run, for every charm |
| #191 | | Handle `SyntaxError` in one place | Otherwise every future AST rule re-implements the same skip |
| #204 | | Normalised `Action`/`ConfigOption` objects | Each actions/config rule re-derives the same shape |
| #242 | | Shared Pebble layer discovery | Blocks the layer rules (PEB003, #234, #173) from sharing one discovery |
| #212 | | Give rules the repository root and its workflows | Blocks every CI-shaped rule (#276, #278, #309, #310, #311, #314, and the listing-review items) |
| #260 | | Iterate over well-formed observers | Every event-handler rule re-derives "is this a usable handler"; CORRECTNESS-004 is the current example |
| #266 | | Gather every `ops` declaration and pick by section role | 245 of 417 charms declare `ops` more than once; first-hit is wrong in principle and already wrong twice in the corpus |
| #265 | | Validate `pyproject.toml` shape once in the core | Otherwise every rule guards with its own `isinstance` ladder |
| #263 | | Resolve charm base classes defined in the charm's own tree | Subclasses of a local base are silently skipped by every AST rule |
| #200 | | Parse URLs in one place, report non-URLs | METADATA-010 swallows values that are not URLs at all |
| #206 | | Decide centrally whether placeholder library charms are in scope | Currently the largest single source of genuine FPs, re-litigated per rule |
| #252 | | Resolve config per charm, not per run | Since #240 a run covers many charms, and a charm's own `[tool.charmlint]` is silently ignored |
| #236 | | Report suppressed diagnostics in JSON | A consumer cannot tell "passes" from "silenced" |
| #315 | | Report whether each rule actually ran | The same gap as #236 for a skipped file or a crashed rule; #316 is blocked on it |
| #177 | | Inline per-line suppression (`noqa`-style) | #236 says suppression already works; confirm what ships before starting |
| #254 | | Ruff-style range suppression (disable/enable) | Follows #177 |
| #258 | | Report suppression comments that aren't suppressing anything | Follows #177 |
| #267 | | Make a leftover `# charmlint: noqa` directive an error | Follows #177 |
| #259 | | Make rule-name validation aware of preview rules | Blocks shipping anything as preview |
| #175 | | Optional `breaks_backwards_compatibility` flag on rules | Wanted before the next batch of rules lands, not retrofitted |
| #176 | | LIBRARY-001: use the charmlibs `libs.yaml` as the deprecation map | Hand-maintained map goes stale; see also #198 |
| #192 | | Split `_rules/correctness.py` | Four CORRECTNESS rules have landed — this is now due |
| #261 | | Ledger of the rules that need type information | Several rules match on names instead; the list stops us re-litigating it one review at a time |

## Phase 2 — Rules that are ready to review

Non-draft PRs. Finishing these is the shortest path to shipped value,
and several of them are the implementation of an issue listed further
down.

| PR | Rule | State |
|---|---|---|
| #245, #246, #247, #248 | the Phase 0 false-positive fixes | ready |
| #253 | RELATIONS-003 (unordered-value-in-databag) — implements #229 | ready |
| #46 | FEATURES-005/006 (workload version) | approved, but still wants the #206 decision; see Phase 6 |

## Phase 3 — Tier A rules: runtime failures, high yield, low FP risk

The charm is broken at hook runtime, the corpus says it happens
often, and detection is a literal-string or declared-name comparison.

| Rule | Issue | PR | Evidence |
|---|---|---|---|
| Unguarded `yaml.safe_load()`/`json.loads()` of config and relation data | #220 | | 42 of 136 charms; 18 independently proposed the rule |
| Config parsing in `__init__` that can raise before any status is set | #221 | | The severe subset of #220 — the charm is stuck until `juju resolved`; #270 overlaps |
| `get_container()` name not declared in `containers:` | #149 | #207 | error, near-zero FP |
| Juju secret read without catching `SecretNotFoundError`/`ModelError` | #230 | | Normal states (not yet granted) raise |
| `ActiveStatus` reported without checking the Pebble service is running | #234 | | ~22 of 136 charms, ~10 mechanically checkable; wants #242 |
| Relation observed for joined/changed but never departed/broken | #237 | | ~20 of 136 charms |
| Unit status compared (`==`) instead of assigned | #152 | | error, near-zero FP |
| No return after `event.fail()` / early `set_results()` | #153 | | error |
| `container.restart()`/`replan()` without `ChangeError` handling | #154 | | |
| Privileged command, or a write outside the charm dir, on a `non-root` charm | #249 | | The pair of findings that decide a non-root migration; CHARMCRAFT-008/009 only read the YAML |
| `ActiveStatus` added unconditionally in a collect-status handler | #233 | | Defeats the point of `collect_unit_status` |
| Truthiness check on an int/bool-typed config option | #151 | | `if self.config["port"]:` silently drops 0/False |
| `cached_property` on a charm or an object it constructs | #226 | | Steady supply of corpus bugs |

## Phase 4 — Tier B rules: migration, deprecation, security

Mechanical to detect, and each one is a thing that is already broken
or about to break on a Juju/charmcraft version bump.

**Migration and deprecation**

| Rule | Issue | PR | Evidence |
|---|---|---|---|
| Charm targets an end-of-life base | #201 | | 73 of 551 charms; 27 have no supported base at all. Needs an ID — CHARMCRAFT-006 is taken |
| Integration tests never run against Juju 4 | #309 | | Nothing tells a charm its tests only prove Juju 3; wants #212 |
| Docs use `juju run-action`, removed in Juju 3 | #224 | | Documented command cannot succeed |
| `unit.open_port()`/`close_port()` instead of `set_ports()` | #164 | | |
| `charmhelpers` imported in an ops charm | #165 | | |
| Direct `os.environ` `JUJU_*` access | #166 | | |
| Juju hook tools invoked via subprocess | #167 | | |
| Tracing wiring: endpoint name mismatch, removed `ops_tracing.setup()` | #161 | | |
| Integration tests on pytest-operator/python-libjuju | #162 | | |
| Jubilant misuse | #163 | | |
| `testing.Context` with legacy `meta=`/`config=` kwargs | #277 | | |
| Manual config/param parsing where `load_config()`/`load_params()` exist | #168 | | |
| Old-style `__init__(self, *args)` boilerplate | #169 | | |

**Security**

| Rule | Issue |
|---|---|
| Action results return file contents that look like key material | #225 |
| Secret content passed as a subprocess CLI argument | #287 |
| Sensitive value in logs | #289 |
| Hardcoded default on a secret config option | #275 |
| Sensitive config file written without `chmod` | #288 |
| OCI `upstream-source` pinned by tag rather than digest | #269 |
| Machine charm downloads without an integrity check | #284 |
| Charm uses Juju secrets but never observes `secret-changed` | #26 |

## Phase 5 — Tier C rules: drift and dead declarations

Real defects, lower blast radius: the charm works, but something it
declares or documents is wrong.

| Rule | Issue | PR |
|---|---|---|
| README documents actions or endpoints the charm doesn't declare | #232 | |
| Relation endpoint declared in metadata but never used in code | #227 | |
| Library under `lib/charms` that nothing imports | #228 | |
| Tests disabled by a module-level skip or xfail | #231 | |
| Integration tests that no CI workflow runs | #310 | |
| Numeric config option with no minimum or maximum | #222 | 13 charms proposed it |
| Config description enumerates values it doesn't constrain | #223 | 12 charms proposed it |
| Terraform module endpoints drift from `charmcraft.yaml` | #235 | 97 of 136 charms ship a module, nothing checks it |
| Relation data aggregated with plain assignment in a loop over relations | #156 | |
| `MaintenanceStatus` with an exit path that never restores status | #157 | |
| `BlockedStatus`/`WaitingStatus` semantics mixed up in the message | #158 | |
| Shipped Grafana dashboard JSON (hardcoded uid, non-COS variables) | #159 | |
| Shipped Prometheus/Loki alert rules (empty matchers, `for: 0m`) | #160 | |
| Interface definitions linted against the OP083 spec | #256 | Dropped from 26.10 and 27.04; pydantic-shaped |
| Unknown keys inside config/action bodies | #179 | |
| Full charmcraft schema, starting with underscored action names | #174 | |
| Actions/config in both `charmcraft.yaml` and the legacy file | #171 | |
| Config option duplicating a `juju model-config` key | #214 | |
| Deprecated charmcraft `charm` plugin | #215 | |
| External command output not captured | #216 | |
| Checked-in `dispatch`: flag it, and flag one that can't be analysed | #217 | |
| Pebble notices checked correctly | #173 | |
| Mixed `self.framework.observe` / `framework.observe` | #31 | |
| Build artefacts not gitignored | #32 | |
| `requirements.txt` alongside `uv.lock` | #28 | |
| Documentation links returning 301/308 | #33 | |
| Storage declared without a storage-attached observer | #273 | |
| `except Exception` that neither logs nor re-raises | #272 | |
| `time.sleep()` in charm source | #271 | |
| Vendored libs without a `charm-libs` declaration | #283 | |
| `collect_app_status` without an `is_leader` guard | #290 | |
| `ActiveStatus()` with no message in a multi-role charm | #285 | |
| K8s charm with Pebble containers tested only with Harness | #286 | |
| Relation data read by subscript with no guard and no schema | #292 | |
| `loki_push_api` required without a `LogForwarder` | #281 | |
| OCI image missing `upstream-source` | | #58 |

## Phase 6 — Tier D: decide before writing

These prescribe a feature rather than finding a defect, or fire on a
large fraction of the fleet by design. They need a decision on scope
(and most of them need #206) before more review time goes into them.

| Rule | Issue | PR | The question |
|---|---|---|---|
| `platforms:` covers amd64 only | #203 | | 140 of 370 charms; many are amd64-only for good reason. Narrow to framework extensions? Needs a new ID — CHARMCRAFT-008 has landed as `charm-user` |
| Flapping databags | #251 | | Borrow from flaplint, run it, or rebuild on our AST walking? #229/#253 is the first piece |
| No diagnostic action | #279 | | Is "should have this action" charmlint's business? |
| No restart/replan/reload action | #282 | | Same |
| Stateful charm without backup/restore actions | #280 | | Same |
| Charm with peers but no leader-elected observer | #274 | | Same |
| No `set_workload_version()` | | #46 | Approved, but 9 of 84 findings are fixture charms — needs #206 |
| No `config-changed` observer | | #54 | |
| No `upgrade-charm` observer | | #23 | |
| Pebble health check coverage | | #45 | |
| Description must mention required relations | #291 | | |
| No CI workflow / no dependency updates | #276, #278 | | Blocked on #212 |
| No security scanning in CI | #314 | | Ruff already carries bandit's rules, so is the narrow dependency/image-scanning version the rule? Third member of the #276/#278 family |
| Missing CONTRIBUTING, SECURITY and CHANGELOG | #311 | | Three rules or one? They live at the repository root, so wants #212 |
| No release-notes process | #312 | | Prescribes one Canonical tool and one layout; a third of PQF's check is a GitHub API call we won't make |
| SECURITY.md silent on CVEs and security updates | #313 | | Three keywords in a markdown file is a weak signal in both directions |
| PQF preflight output format | #316 | | Whole-feature decision, not a rule; blocked on #315 |
| No type annotations | | #140 | Fires on a large fraction of the fleet |
| PERFORMANCE-001/002 | | #44, #42 | +700 lines each for an info-severity finding |
| AI optional extra | #36 | | Whole-feature decision, not a rule |
| Race conditions from the reconcile approach | #308 | | From the 26.10 survey; may be hypothesis-style charm tests rather than a lint rule at all |

## Restoration ledger

The remaining half of #94. Groups collapse where the rules share a
module or a factory. The drafts cut from `refactor/strip-rules` have
all been closed now, so each outstanding group is an issue describing
what the rule did and what it would take to write it again; the branch
survives in each case if the old implementation is worth reading.

| Group | Old IDs | New IDs | PR | Status |
|---|---|---|---|---|
| METADATA | META001–007 | METADATA-001–007 | #95 | landed |
| METADATA optional/website | META008–010 | METADATA-008–010 | #49, #188 | landed |
| CHARMCRAFT | CC001–CC006 | CHARMCRAFT-001–006 | #106–#110 | landed |
| ACTIONS | ACT004–ACT006 (ACTIONS-002 is new) | ACTIONS-001–004 | #104, #182, #189 | landed |
| CONFIG | CFG001–CFG003 | CONFIG-001–003 | #180 | landed |
| DOCUMENTATION | DOC001 | DOCUMENTATION-001 | #123 | landed |
| LIBRARY | LIB001 | LIBRARY-001 | #130 | landed |
| SECURITY | SEC001 | SECURITY-001 | #136 | landed |
| STRUCTURE | STR001, STR002 | STRUCTURE-001, -002 | #138, #139 | landed |
| TESTING | TEST001 | TESTING-001 | #141 | landed |
| TEST003 | TEST003 | TESTING-003 | #143 | landed |
| PEBBLE | (new) | PEBBLE-005 | #194 | landed |

| Group | Old IDs | New IDs | Issue | Notes |
|---|---|---|---|---|
| COS 001–004 | COS001–COS004 | OBSERVABILITY-00x | #293 | |
| COS 005 | COS005 | OBSERVABILITY-00x | #294 | |
| STS 001–003 | STS001–STS003 | STATUS-00x | #295 | renumber after STATUS-001 |
| DEP 001–004 | DEP001–DEP004 | DEPRECATION-00x | #296 | |
| ACT 001–003 | ACT001–ACT003 | ACTIONS-00x | #297 | Tier D shape: "expected operational actions" |
| ACT007 | ACT007 | ACTIONS-00x | #298 | |
| ATT001/002 | ATT001, ATT002 | ATTESTATION-001/002 | #299 | |
| PEB001–003 | PEB001–PEB003 | PEBBLE-001–003 | #300 | one issue for all three; PEB003 wants #242 |
| CFG004 | CFG004 | CONFIG-004 | | no issue yet; CONFIG-006 is its inverse, so decide whether it's still wanted |
| CFG005 | CFG005 | CONFIG-005 | #301 | |
| DOC002–005 | DOC002–DOC005 | DOCUMENTATION-00x | #302 | Tier D; should come back as one rule rather than four |
| LIB002 | LIB002 | LIBRARY-002 | #303 | |
| LIB003/004 | LIB003, LIB004 | LIBRARY-003/004 | #304 | |
| REL001/002 | REL001, REL002 | RELATIONS-001/002 | #305 | |
| SEC002 | SEC002 | SECURITY-002 | #306 | Tier D (no-tls-support) |
| STR003 | STR003 | STRUCTURE-003 | | still an open draft, #140; Tier D |
| TEST002 | TEST002 | TESTING-002 | #307 | Tier D; #162 and #163 say more and should go first |

## Housekeeping

**ID collisions to settle.** #201 asks for CHARMCRAFT-006, which
`no-ops-main-call` (#109) already holds. #203 asks for CHARMCRAFT-008,
which has now landed as `charm-user` (#241). #253 claims RELATIONS-003
while RELATIONS-001/002 are still unwritten (#305). Issues #148–#171
and #26–#33 were all filed under the pre-renumber `PREFIX###` scheme
and need `CATEGORY-###` IDs assigned when they are picked up — the
number in the title is not reserved.

**Duplicates to close.** #238 is the issue for the Harness rule that
landed as TESTING-003 in #143 — close it. #148 is the issue for the
`observe()` rule that landed as CORRECTNESS-008 in #250, so close that
one too. #149/#207 and #229/#253 are issue/PR pairs; close the issue
when the PR lands. #35 (rename `STS` → `STAT`) is obsolete: the
category is `STATUS` under the full-word scheme in
`docs/id-scheme.md`, and STATUS-001 has shipped.

**The draft backlog is cleared.** The 64 stale drafts are closed, each
with an issue carrying what the draft knew, so the numbers in this
file are issues now rather than branches. Fourteen PRs are left: the
four Phase 0 fixes, #253 and #46, and eight drafts. Six of those
drafts are Tier D and will not be reviewed soon; the other two are
#207 (Tier A) and #58 (Tier C).

## Process for a rule PR

1. One rule (or one factory group) per PR; helpers land in their own
   gating PR first where a group shares them.
2. Restore or add the rule code, its tests, the `_rules/__init__.py`
   import if a whole module returns, and any `docs/` references.
3. Run the rule over the local hyrum charm cache and put the results in
   the PR body: charms scanned, charms with findings, findings by
   severity, a `| Rule | TP | FP | UNK | Total |` table, and prose
   naming the charms and files behind each finding. If the FP rate is
   not ~0%, tighten the rule and run it again.
4. `make test && make lint` locally before pushing.
