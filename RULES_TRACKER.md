# charmlint work tracker

This tracks **all** outstanding charmlint work, not just the rules
refactor: the rules that are still to be restored from the strip, the
new rules that have been proposed since, the engine work they depend
on, and the bugs in rules that already ship.

As of 2026-09-14 there are 71 open PRs and 85 open issues. That queue
is longer than the team can review in the order it was opened, so the
sections below are ordered by expected value rather than by number.

## Where we are

40 rules are registered, across 12 modules:

| Category | Landed |
|---|---|
| ACTIONS | 001, 002, 003, 004 |
| CHARMCRAFT | 001–009 |
| CONFIG | 001, 002, 003, 006 |
| CORRECTNESS | 001, 002, 003, 004 |
| DOCUMENTATION | 001 |
| LIBRARY | 001 |
| METADATA | 001–010 |
| PEBBLE | 005 |
| SECURITY | 001 |
| STATUS | 001 |
| STRUCTURE | 001, 002 |
| TESTING | 001, 003 |

The strip-and-re-add refactor (#94) is half done: of the 61 pre-strip
rule IDs, 31 are back, and the rest are listed in the restoration
ledger below. The other nine registered rules are new since the strip.
Every rule still lands via its own PR.

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
| #212 | | Give rules the repository root and its workflows | Blocks every CI-shaped rule (#52, #59, and the listing-review items) |
| #260 | | Iterate over well-formed observers | Every event-handler rule re-derives "is this a usable handler"; CORRECTNESS-004 is the current example |
| #266 | | Gather every `ops` declaration and pick by section role | 245 of 417 charms declare `ops` more than once; first-hit is wrong in principle and already wrong twice in the corpus |
| #265 | | Validate `pyproject.toml` shape once in the core | Otherwise every rule guards with its own `isinstance` ladder |
| #263 | | Resolve charm base classes defined in the charm's own tree | Subclasses of a local base are silently skipped by every AST rule |
| #200 | | Parse URLs in one place, report non-URLs | METADATA-010 swallows values that are not URLs at all |
| #206 | | Decide centrally whether placeholder library charms are in scope | Currently the largest single source of genuine FPs, re-litigated per rule |
| #252 | | Resolve config per charm, not per run | Since #240 a run covers many charms, and a charm's own `[tool.charmlint]` is silently ignored |
| #236 | | Report suppressed diagnostics in JSON | A consumer cannot tell "passes" from "silenced" |
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
| #67 | SUPPLYCHAIN-005/006 (ops pinning) | approved |
| #245, #246, #247, #248 | the Phase 0 false-positive fixes | ready |
| #253 | RELATIONS-003 (unordered-value-in-databag) — implements #229 | ready |
| #257 | only import `importlib.metadata` for `--version` | ready |

## Phase 3 — Tier A rules: runtime failures, high yield, low FP risk

The charm is broken at hook runtime, the corpus says it happens
often, and detection is a literal-string or declared-name comparison.

| Rule | Issue | PR | Evidence |
|---|---|---|---|
| Unguarded `yaml.safe_load()`/`json.loads()` of config and relation data | #220 | | 42 of 136 charms; 18 independently proposed the rule |
| Config parsing in `__init__` that can raise before any status is set | #221 | #20 (CORR007, overlaps) | The severe subset of #220 — the charm is stuck until `juju resolved` |
| `observe()` references a handler or event that cannot exist | #148 | #250 | error, near-zero FP |
| `get_container()` name not declared in `containers:` | #149 | #207 | error, near-zero FP |
| Juju secret read without catching `SecretNotFoundError`/`ModelError` | #230 | | Normal states (not yet granted) raise |
| `ActiveStatus` reported without checking the Pebble service is running | #234 | | ~22 of 136 charms, ~10 mechanically checkable; wants #242 |
| Relation observed for joined/changed but never departed/broken | #237 | #65 (EVNT001, narrower) | ~20 of 136 charms |
| Unit status compared (`==`) instead of assigned | #152 | #63 (JUJU001/007) | error, near-zero FP |
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
| Docs use `juju run-action`, removed in Juju 3 | #224 | | Documented command cannot succeed |
| `unit.open_port()`/`close_port()` instead of `set_ports()` | #164 | | |
| `charmhelpers` imported in an ops charm | #165 | | |
| Direct `os.environ` `JUJU_*` access | #166 | | |
| Juju hook tools invoked via subprocess | #167 | | |
| Tracing wiring: endpoint name mismatch, removed `ops_tracing.setup()` | #161 | | |
| Integration tests on pytest-operator/python-libjuju | #162 | | |
| Jubilant misuse | #163 | | |
| `testing.Context` with legacy `meta=`/`config=` kwargs | | #55 | |
| Manual config/param parsing where `load_config()`/`load_params()` exist | #168 | | |
| Old-style `__init__(self, *args)` boilerplate | #169 | | |

**Security**

| Rule | Issue | PR |
|---|---|---|
| Action results return file contents that look like key material | #225 | |
| Secret content passed as a subprocess CLI argument | | #74 |
| Sensitive value in logs | | #76 |
| Hardcoded default on a secret config option | | #51 |
| Sensitive config file written without `chmod` | | #75 |
| OCI `upstream-source` not SHA-pinned | | #19 |
| Machine charm downloads without an integrity check | | #70 |
| Charm uses Juju secrets but never observes `secret-changed` | #26 | #73 (rotate/expiry — sibling, not the same) |

## Phase 5 — Tier C rules: drift and dead declarations

Real defects, lower blast radius: the charm works, but something it
declares or documents is wrong.

| Rule | Issue | PR |
|---|---|---|
| README documents actions or endpoints the charm doesn't declare | #232 | |
| Relation endpoint declared in metadata but never used in code | #227 | |
| Library under `lib/charms` that nothing imports | #228 | |
| Tests disabled by a module-level skip or xfail | #231 | |
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
| Storage declared without a storage-attached observer | | #41 |
| Silently-swallowed `except Exception` | | #39 |
| `time.sleep()` in charm source | | #37 |
| Vendored libs without a `charm-libs` declaration | | #69 |
| `collect_app_status` without an `is_leader` guard | | #77 |
| `ActiveStatus()` with no message in a multi-role charm | | #71 |
| K8s charm with Pebble containers tested only with Harness | | #72 |
| Relation data validated without a structured schema | | #79 |
| `loki_push_api` required without a `LogForwarder` | | #64 |
| OCI image missing `upstream-source` | | #58 |

## Phase 6 — Tier D: decide before writing

These prescribe a feature rather than finding a defect, or fire on a
large fraction of the fleet by design. They need a decision on scope
(and most of them need #206) before more review time goes into them.

| Rule | Issue | PR | The question |
|---|---|---|---|
| `platforms:` covers amd64 only | #203 | | 140 of 370 charms; many are amd64-only for good reason. Narrow to framework extensions? Needs a new ID — CHARMCRAFT-008 has landed as `charm-user` |
| Flapping databags | #251 | | Borrow from flaplint, run it, or rebuild on our AST walking? #229/#253 is the first piece |
| No diagnostic action | | #60 | Is "should have this action" charmlint's business? |
| No restart/replan/reload action | | #68 | Same |
| Stateful charm without backup/restore actions | | #62 | Same |
| Stateful charm without a leader-elected handler | | #50 | Same |
| No `set_workload_version()` | | #46 | 9 of 84 findings are fixture charms — needs #206 |
| No `assumes:` juju version | | #22 | All 7 FPs are placeholder charms — needs #206 |
| No `config-changed` observer | | #54 | |
| No `upgrade-charm` observer | | #23 | |
| Pebble health check coverage | | #45 | |
| Description must mention required relations | | #78 | |
| No CI workflow / no dependency updates | | #52, #59 | Blocked on #212 |
| No type annotations | | #140 | Fires on a large fraction of the fleet |
| PERFORMANCE-001/002 | | #44, #42 | +700 lines each for an info-severity finding |
| AI optional extra | #36 | | Whole-feature decision, not a rule |

## Restoration ledger

The remaining half of #94. Groups collapse where the rules share a
module or a factory. Every one of these has a draft PR cut from
`refactor/strip-rules` unless noted.

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
| COS 001–004 | COS001–COS004 | OBSERVABILITY-00x | #96 | draft |
| COS 005 | COS005 | OBSERVABILITY-00x | #97 | draft |
| STS 001–003 | STS001–STS003 | STATUS-00x | #98 | draft, renumber after STATUS-001 |
| DEP 001–004 | DEP001–DEP004 | DEPRECATION-00x | #99 | draft |
| ACT 001–003 | ACT001–ACT003 | ACTIONS-00x | #100 | draft (Tier D shape: "expected operational actions") |
| ACT007 | ACT007 | ACTIONS-00x | #103 (helpers), #105 | draft |
| ATT001/002 | ATT001, ATT002 | ATTESTATION-001/002 | #111 (helpers), #112, #113 | draft |
| PEB001 | PEB001 | PEBBLE-001 | #114 (helpers), #115 | draft |
| PEB002 | PEB002 | PEBBLE-002 | #116 **closed** | needs a new PR |
| PEB003 | PEB003 | PEBBLE-003 | #117 | draft |
| CFG004 | CFG004 | CONFIG-004 | #121 **closed** | needs a new PR; CONFIG-006 is its inverse |
| CFG005 | CFG005 | CONFIG-005 | #122 | draft |
| DOC002–005 | DOC002–DOC005 | DOCUMENTATION-00x | #124 (helpers), #125–#128 | draft, Tier D |
| LIB002 | LIB002 | LIBRARY-002 | #129 (helpers), #131 | draft |
| LIB003/004 | LIB003, LIB004 | LIBRARY-003/004 | #132 | draft |
| REL001/002 | REL001, REL002 | RELATIONS-001/002 | #133 (helpers), #134, #135 | draft |
| SEC002 | SEC002 | SECURITY-002 | #137 | draft, Tier D (no-tls-support) |
| STR003 | STR003 | STRUCTURE-003 | #140 | draft, Tier D |
| TEST002 | TEST002 | TESTING-002 | #142 | draft, Tier D |

## Housekeeping

**ID collisions to settle.** #201 asks for CHARMCRAFT-006, which
`no-ops-main-call` (#109) already holds. #203 asks for CHARMCRAFT-008,
which has now landed as `charm-user` (#241). #253 claims RELATIONS-003
while RELATIONS-001/002 are still in draft (#134, #135). Issues
#148–#171 and #26–#33 were all filed under the pre-renumber
`PREFIX###` scheme and need `CATEGORY-###` IDs assigned when they are
picked up — the number in the title is not reserved.

**Duplicates to close.** #238 is the issue for the Harness rule that
landed as TESTING-003 in #143 — close it. #149/#207, #229/#253 and
#152/#63 are issue/PR pairs; close the issue when the PR lands. #35
(rename `STS` → `STAT`) is obsolete: the category is `STATUS` under
the full-word scheme in `docs/id-scheme.md`, and STATUS-001 has
shipped.

**Stale drafts.** 64 of the 71 open PRs are drafts, most untouched
since late August, and the Tier D ones will not be reviewed soon.
Better to close them with a pointer from the tracking issue than to
keep them open and rebasing.

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
