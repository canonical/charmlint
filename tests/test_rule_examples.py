"""Tests that each rule's documented example and fix behave as documented."""

import pathlib

import pytest

from charmlint._config import LintConfig
from charmlint._linter import lint
from charmlint._rules import Rule, get_all_rules

_EXAMPLE_RULES = [rule for rule in get_all_rules().values() if rule.example]

# Rules whose fix can't be written as files laid over the example: the
# LIBRARY-001 fix is deleting the vendored library.
_NO_EXAMPLE = {"LIBRARY-001"}


def test_every_rule_has_an_example():
    missing = sorted(set(get_all_rules()) - {r.id for r in _EXAMPLE_RULES} - _NO_EXAMPLE)
    assert not missing, f"Rules without an example and fix: {', '.join(missing)}"


@pytest.mark.parametrize("rule", _EXAMPLE_RULES, ids=lambda rule: rule.id)
def test_example_is_reported(rule: Rule, tmp_path: pathlib.Path):
    assert rule.example is not None
    _write(tmp_path, rule.example)
    assert _hits(rule, tmp_path), f"{rule.id} does not report its own example"


@pytest.mark.parametrize("rule", _EXAMPLE_RULES, ids=lambda rule: rule.id)
def test_fix_is_not_reported(rule: Rule, tmp_path: pathlib.Path):
    assert rule.example is not None
    assert rule.fix is not None
    _write(tmp_path, {**rule.example, **rule.fix})
    assert not _hits(rule, tmp_path), f"{rule.id} still reports its example once fixed"


def _write(charm_dir: pathlib.Path, files: dict[str, str]) -> None:
    for path, text in files.items():
        target = charm_dir / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)


def _hits(rule: Rule, charm_dir: pathlib.Path) -> list[str]:
    report = lint(charm_dir, LintConfig(select=[rule.id]))
    return [d.message for d in report if d.rule_id == rule.id]
