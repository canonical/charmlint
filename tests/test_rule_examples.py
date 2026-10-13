"""Tests that each rule's documented example and fix behave as documented."""

import collections
import pathlib

import pytest

from charmlint._config import LintConfig
from charmlint._linter import lint
from charmlint._rules import Rule, get_all_rules

_EXAMPLE_RULES = [rule for rule in get_all_rules().values() if rule.example]

# Rules that don't have an example and fix yet. A new rule is expected to
# come with one; adding its ID here instead is a deliberate, visible choice
# for review, and the entry goes again when the example is written.
_AWAITING_EXAMPLE: frozenset[str] = frozenset()


def test_every_rule_has_an_example():
    missing = sorted(set(get_all_rules()) - {r.id for r in _EXAMPLE_RULES} - _AWAITING_EXAMPLE)
    assert not missing, (
        f"Rules without an example and fix: {', '.join(missing)}. "
        "Set `example` and `fix` on the rule class (see `Rule`)."
    )


def test_awaiting_example_lists_only_rules_still_without_one():
    # Keeps the allowlist from outliving the gap it covers.
    stale = sorted(_AWAITING_EXAMPLE & {r.id for r in _EXAMPLE_RULES})
    unknown = sorted(_AWAITING_EXAMPLE - set(get_all_rules()))
    assert not stale, f"Remove from _AWAITING_EXAMPLE, these have examples now: {stale}"
    assert not unknown, f"Remove from _AWAITING_EXAMPLE, these are not rules: {unknown}"


@pytest.mark.parametrize("rule", _EXAMPLE_RULES, ids=lambda rule: rule.id)
def test_example_is_reported_once(rule: Rule, tmp_path: pathlib.Path):
    assert rule.example is not None
    _write(tmp_path, rule.example)
    hits = _hits(rule, tmp_path)
    assert len(hits) == 1, f"{rule.id} reports its example {len(hits)} times, not once: {hits}"


@pytest.mark.parametrize("rule", _EXAMPLE_RULES, ids=lambda rule: rule.id)
def test_fix_is_not_reported(rule: Rule, tmp_path: pathlib.Path):
    assert rule.example is not None
    assert rule.fix is not None
    _write(tmp_path, {**rule.example, **rule.fix})
    assert not _hits(rule, tmp_path), f"{rule.id} still reports its example once fixed"


@pytest.mark.parametrize("rule", _EXAMPLE_RULES, ids=lambda rule: rule.id)
def test_fix_reports_nothing_new(rule: Rule, tmp_path: pathlib.Path):
    # A fix that stopped the rule firing by removing what it reads, or that
    # doesn't parse, or that trips a different rule, isn't the fix to show.
    # Lines can move when a fix adds or removes some, so findings are
    # compared by rule and file.
    assert rule.example is not None
    assert rule.fix is not None
    before_dir = tmp_path / "example"
    after_dir = tmp_path / "fixed"
    _write(before_dir, rule.example)
    _write(after_dir, {**rule.example, **rule.fix})
    new = _findings(after_dir) - _findings(before_dir)
    assert not new, f"{rule.id}'s fix introduces new findings: {sorted(new.elements())}"


def _write(charm_dir: pathlib.Path, files: dict[str, str] | dict[str, str | None]) -> None:
    for path, text in files.items():
        if text is None:
            continue
        target = charm_dir / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)


def _hits(rule: Rule, charm_dir: pathlib.Path) -> list[str]:
    report = lint(charm_dir, LintConfig(select=[rule.id]))
    return [d.message for d in report if d.rule_id == rule.id]


def _findings(charm_dir: pathlib.Path) -> collections.Counter[tuple[str, str | None]]:
    return collections.Counter((d.rule_id, d.path) for d in lint(charm_dir))
