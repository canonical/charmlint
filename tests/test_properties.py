"""Property-based tests for the charmlint rule engine.

The example tests (``test_linter.py``, ``test_rules.py``) cover
canonical charm shapes; this suite throws structurally-valid but
semantically arbitrary ``charmcraft.yaml`` dicts at ``lint()`` and
pins down invariants that should hold across every rule.

Invariants under test:

* *Understood.*  ``lint()`` returns a report with no ``FATAL`` for any
  structurally-valid metadata dict, including empty endpoint maps,
  empty option lists, and surprising (but valid) defaults: every rule
  ran, and none raised.
* *Deterministic.*  Running ``lint()`` twice back-to-back against
  the same directory must produce the same diagnostics in the same
  order — the engine should not depend on rule-iteration order,
  environment, or time. (Both runs share one process, so this can't
  catch a dependence on the hash seed.)
* *Well-formed diagnostics.*  Every ``Diagnostic`` names a registered
  rule, has a valid ``Severity`` enum value and a non-empty
  ``message``, and only ever has a ``line`` alongside a ``path``.
"""

from __future__ import annotations

import pathlib
import string

import yaml
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from charmlint._linter import lint
from charmlint._models import Severity
from charmlint._rules import get_all_rules

# Hypothesis warns when a @given test uses a function-scoped pytest
# fixture because the fixture is created once and then reused across
# every generated example — a common source of subtle state leaks.
# In this file that reuse is deliberate: each property body overwrites
# ``tmp_charm/charmcraft.yaml`` and touches no other state, so a shared
# directory is equivalent to a fresh one per example. Suppress the
# health check globally for the module. ``max_examples`` is Hypothesis's
# default.
_charm_settings = settings(
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


# Charm/endpoint/action names follow ``^[a-z][a-z0-9-]*$`` in practice; keep the
# alphabet tight so Hypothesis shrinks to readable failing examples.
_name = st.text(alphabet=string.ascii_lowercase + "-", min_size=1, max_size=10).filter(
    lambda s: s[0] != "-" and s[-1] != "-"
)

# Free-form human-readable text — intentionally boring; the rule engine
# doesn't care about the contents, only about whether fields are present.
_safe_text = st.text(alphabet=string.ascii_letters + " .", min_size=0, max_size=30)


def _endpoints_map() -> st.SearchStrategy[dict]:
    """A 0..3-entry map of endpoint name → ``{"interface": str}``."""
    return st.dictionaries(
        _name,
        st.fixed_dictionaries({"interface": _name}),
        max_size=3,
    )


def _config_options_map() -> st.SearchStrategy[dict]:
    """A 0..3-entry map of option name → option spec dict."""
    option_value = st.one_of(
        st.text(max_size=10),
        st.integers(min_value=-1000, max_value=1000),
        st.booleans(),
    )
    return st.dictionaries(
        _name,
        st.fixed_dictionaries({
            "type": st.sampled_from(["string", "int", "boolean"]),
            "description": _safe_text,
            "default": option_value,
        }),
        max_size=3,
    )


def _actions_map() -> st.SearchStrategy[dict]:
    """A 0..3-entry map of action name → ``{"description": str}``."""
    return st.dictionaries(
        _name,
        st.fixed_dictionaries({"description": _safe_text}),
        max_size=3,
    )


@st.composite
def _charmcraft_metadata(draw: st.DrawFn) -> dict:
    """Build a plausible ``charmcraft.yaml`` dict.

    ``name`` is always present (required by the rules engine); every
    other field is optionally omitted, so the generated space covers
    both "minimal charm" and "everything filled in" shapes.
    """
    meta: dict = {"name": draw(_name)}
    if draw(st.booleans()):
        meta["summary"] = draw(_safe_text)
    if draw(st.booleans()):
        meta["description"] = draw(_safe_text)
    if draw(st.booleans()):
        meta["display-name"] = draw(_safe_text)
    if draw(st.booleans()):
        meta["requires"] = draw(_endpoints_map())
    if draw(st.booleans()):
        meta["provides"] = draw(_endpoints_map())
    if draw(st.booleans()):
        meta["peers"] = draw(_endpoints_map())
    if draw(st.booleans()):
        meta["config"] = {"options": draw(_config_options_map())}
    if draw(st.booleans()):
        meta["actions"] = draw(_actions_map())
    return meta


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_and_lint(tmp_charm: pathlib.Path, metadata: dict):
    """Write *metadata* to ``tmp_charm/charmcraft.yaml`` and run ``lint()``.

    The fixture re-creates ``tmp_charm`` between tests but not between
    Hypothesis examples; the charmcraft.yaml is overwritten on each
    call so prior examples don't leak.
    """
    (tmp_charm / "charmcraft.yaml").write_text(yaml.dump(metadata))
    return lint(tmp_charm)


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestCharmlintProperties:
    """Invariants of ``lint()`` over arbitrary charmcraft.yaml metadata."""

    @_charm_settings
    @given(metadata=_charmcraft_metadata())
    def test_lint_understands_valid_metadata(
        self, tmp_charm: pathlib.Path, metadata: dict
    ) -> None:
        """Arbitrary valid metadata is linted, not rejected.

        A rule raising would fail the test outright; a ``FATAL`` would
        mean the engine gave up on metadata it should have understood.
        """
        report = _write_and_lint(tmp_charm, metadata)
        assert "FATAL" not in {d.rule_id for d in report}

    @_charm_settings
    @given(metadata=_charmcraft_metadata())
    def test_lint_is_deterministic(self, tmp_charm: pathlib.Path, metadata: dict) -> None:
        """Two consecutive lints over the same dir produce identical diagnostics.

        Rules may iterate dict keys or filesystem entries internally —
        running twice is cheap and catches silent ordering dependencies
        that would cause diff noise in CI runs.
        """
        first = _write_and_lint(tmp_charm, metadata)
        second = lint(tmp_charm)
        # In order, and every field: the report's order is what the user sees.
        assert list(first) == list(second)

    @_charm_settings
    @given(metadata=_charmcraft_metadata())
    def test_diagnostics_are_well_formed(self, tmp_charm: pathlib.Path, metadata: dict) -> None:
        """Every ``Diagnostic`` has populated mandatory fields.

        ``rule_id`` must name a registered rule, severity must be a real
        enum value, and ``message`` must be non-empty. A ``line`` means
        nothing without the ``path`` it is in, though a ``path`` alone is
        fine (a finding about a whole file). A rule that returns a
        blank-message diagnostic would make the ruff-style report
        line unreadable, so pin this down across the whole rule set.
        """
        report = _write_and_lint(tmp_charm, metadata)
        rule_ids = set(get_all_rules())
        for diag in list(report):
            assert diag.rule_id in rule_ids, f"Diagnostic from unknown rule {diag.rule_id!r}"
            assert isinstance(diag.severity, Severity), (
                f"Diagnostic severity is not a Severity: {diag.severity!r}"
            )
            assert diag.message.strip(), f"Diagnostic {diag.rule_id} has empty message"
            # path/line come together — a rule should either point at a
            # specific spot in a file or at neither.
            if diag.line is not None:
                assert diag.path is not None, f"Diagnostic {diag.rule_id} has line but no path"
