"""Property-based tests for the charmlint rule engine.

The example tests (``test_linter.py``, ``test_rules.py``) cover
canonical charm shapes; this suite throws structurally-valid but
semantically arbitrary ``charmcraft.yaml`` files at ``lint()`` and
pins down invariants that should hold across every rule.

The files are YAML text rather than dumped dicts, written the ways
people write YAML: block and flow style, quoted and plain scalars,
block scalars, comments, anchors with aliases and merge keys between
entries, and names that YAML 1.1 reads as booleans or null (``on:``,
``yes:``) whether or not they are quoted. A dict passed through
``yaml.dump`` exercises none of that, and the loader is where a charm
that is valid YAML can still fail to lint.

Invariants under test:

* *Understood.*  ``lint()`` returns a report with no ``FATAL`` for any
  valid ``charmcraft.yaml``, including empty endpoint maps, empty
  option lists, and surprising (but valid) defaults: the file loaded,
  every rule ran, and none raised.
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

import json
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

# Endpoint, option and action names that YAML 1.1 reads as something
# other than a string when they are written unquoted.
_BOOL_LIKE = ("on", "off", "yes", "no", "y", "n", "true", "false", "null", "~")
_key = st.one_of(_name, st.sampled_from(_BOOL_LIKE))

# Free-form human-readable text — intentionally boring; the rule engine
# doesn't care about the contents, only about whether fields are present.
_safe_text = st.text(alphabet=string.ascii_letters + " .", min_size=0, max_size=30)


def _endpoints_map() -> st.SearchStrategy[dict]:
    """A 0..3-entry map of endpoint name → ``{"interface": str}``."""
    return st.dictionaries(
        _key,
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
        _key,
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
        _key,
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


class _Renderer:
    """Write a metadata dict as YAML text, drawing each stylistic choice.

    The result is valid YAML, but deliberately not a faithful copy of the
    dict: an unquoted ``on`` key loads as ``True``, and a merge key pulls
    in a sibling's fields. What matters is that it is a file a charm could
    contain, not that it round-trips.
    """

    def __init__(self, draw: st.DrawFn) -> None:
        self.draw = draw
        self.anchors = 0

    def document(self, metadata: dict) -> str:
        lines = self.block(metadata, 0)
        if self.draw(st.booleans()):
            lines.insert(0, "---")
        return "\n".join(lines) + "\n"

    def block(self, mapping: dict, indent: int) -> list[str]:
        pad = " " * indent
        lines: list[str] = []
        # Anchors of the dict values already written at this level, which
        # a later sibling can alias or merge.
        siblings: list[str] = []
        for key, value in mapping.items():
            if self.draw(st.integers(0, 5)) == 0:
                lines.append(f"{pad}# {self.draw(_safe_text)}".rstrip())
            head = f"{pad}{self.key(key)}:"
            if not isinstance(value, dict):
                lines.extend(self.scalar(head, value, indent + 2))
                continue
            choice = self.draw(st.sampled_from(["block", "flow", "alias", "merge"]))
            if choice in ("alias", "merge") and siblings:
                anchor = self.draw(st.sampled_from(siblings))
                if choice == "alias":
                    lines.append(f"{head} *{anchor}")
                    continue
                lines.append(head)
                lines.append(f"{pad}  <<: *{anchor}")
                lines.extend(self.block(value, indent + 2))
                continue
            if choice == "flow":
                lines.append(f"{head} {self.flow(value)}")
                continue
            anchor = f"a{self.anchors}"
            self.anchors += 1
            siblings.append(anchor)
            lines.append(f"{head} &{anchor}" if value else f"{head} &{anchor} {{}}")
            lines.extend(self.block(value, indent + 2))
        return lines

    def flow(self, mapping: dict) -> str:
        parts = []
        for key, value in mapping.items():
            rendered = self.flow(value) if isinstance(value, dict) else self.inline(value)
            parts.append(f"{self.key(key)}: {rendered}")
        return "{" + ", ".join(parts) + "}"

    def key(self, key: str) -> str:
        # Plain or quoted, whichever is drawn: a plain bool-like key is the
        # point, so it isn't checked to load back as a string.
        if self.draw(st.booleans()) and _plain_scalar(key):
            return key
        return _double_quoted(key)

    def scalar(self, head: str, value: object, indent: int) -> list[str]:
        block_safe = isinstance(value, str) and value.isprintable() and value.strip() == value
        if block_safe and value and self.draw(st.integers(0, 3)) == 0:
            style = self.draw(st.sampled_from(["|-", ">-"]))
            return [f"{head} {style}", " " * indent + value]
        return [f"{head} {self.inline(value)}"]

    def inline(self, value: object) -> str:
        if not isinstance(value, str):
            # An int or a bool: JSON and YAML spell both the same way.
            return json.dumps(value)
        # A control character is only allowed in a file as an escape, which
        # only double quotes have.
        style = self.draw(st.sampled_from(["plain", "single", "double"]))
        if not value.isprintable():
            style = "double"
        if style == "plain" and _loads_as(value, value):
            return value
        if style == "single":
            return "'" + value.replace("'", "''") + "'"
        return _double_quoted(value)


def _double_quoted(text: str) -> str:
    """Write *text* as a YAML double-quoted scalar.

    Not ``json.dumps``: JSON writes a character outside the Basic
    Multilingual Plane as a surrogate pair, which YAML rejects.
    """
    out = []
    for char in text:
        if char in '"\\':
            out.append("\\" + char)
        elif char.isprintable():
            out.append(char)
        elif ord(char) <= 0xFF:
            out.append(f"\\x{ord(char):02x}")
        elif ord(char) <= 0xFFFF:
            out.append(f"\\u{ord(char):04x}")
        else:
            out.append(f"\\U{ord(char):08x}")
    return '"' + "".join(out) + '"'


def _plain_scalar(text: str) -> bool:
    """Whether *text* can be written unquoted as a key at all."""
    try:
        loaded = yaml.safe_load(f"{text}: 1")
    except yaml.YAMLError:
        return False
    return isinstance(loaded, dict) and len(loaded) == 1


def _loads_as(text: str, value: str) -> bool:
    """Whether *text*, written unquoted as a value, loads back as *value*."""
    try:
        return yaml.safe_load(f"k: {text}") == {"k": value}
    except yaml.YAMLError:
        return False


@st.composite
def _charmcraft_yaml(draw: st.DrawFn) -> str:
    """Build the text of a plausible ``charmcraft.yaml``."""
    return _Renderer(draw).document(draw(_charmcraft_metadata()))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_and_lint(tmp_charm: pathlib.Path, text: str):
    """Write *text* to ``tmp_charm/charmcraft.yaml`` and run ``lint()``.

    The fixture re-creates ``tmp_charm`` between tests but not between
    Hypothesis examples; the charmcraft.yaml is overwritten on each
    call so prior examples don't leak.
    """
    (tmp_charm / "charmcraft.yaml").write_text(text)
    return lint(tmp_charm)


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestCharmlintProperties:
    """Invariants of ``lint()`` over arbitrary charmcraft.yaml metadata."""

    @_charm_settings
    @given(text=_charmcraft_yaml())
    def test_lint_understands_valid_metadata(self, tmp_charm: pathlib.Path, text: str) -> None:
        """Arbitrary valid metadata is linted, not rejected.

        A rule raising would fail the test outright; a ``FATAL`` would
        mean the engine gave up on a file it should have understood. The
        file is never empty and always declares a name, so the ``FATAL``
        this can find is the loader refusing valid YAML.
        """
        report = _write_and_lint(tmp_charm, text)
        assert "FATAL" not in {d.rule_id for d in report}

    @_charm_settings
    @given(text=_charmcraft_yaml())
    def test_lint_is_deterministic(self, tmp_charm: pathlib.Path, text: str) -> None:
        """Two consecutive lints over the same dir produce identical diagnostics.

        Rules may iterate dict keys or filesystem entries internally —
        running twice is cheap and catches silent ordering dependencies
        that would cause diff noise in CI runs.
        """
        first = _write_and_lint(tmp_charm, text)
        second = lint(tmp_charm)
        # In order, and every field: the report's order is what the user sees.
        assert list(first) == list(second)

    @_charm_settings
    @given(text=_charmcraft_yaml())
    def test_diagnostics_are_well_formed(self, tmp_charm: pathlib.Path, text: str) -> None:
        """Every ``Diagnostic`` has populated mandatory fields.

        ``rule_id`` must name a registered rule, severity must be a real
        enum value, and ``message`` must be non-empty. A ``line`` means
        nothing without the ``path`` it is in, though a ``path`` alone is
        fine (a finding about a whole file). A rule that returns a
        blank-message diagnostic would make the ruff-style report
        line unreadable, so pin this down across the whole rule set.
        """
        report = _write_and_lint(tmp_charm, text)
        rule_ids = set(get_all_rules())
        for diag in list(report):
            assert diag.rule_id in rule_ids, f"Diagnostic from unknown rule {diag.rule_id!r}"
            assert isinstance(diag.severity, Severity), (
                f"Diagnostic severity is not a Severity: {diag.severity!r}"
            )
            assert diag.message.strip(), f"Diagnostic {diag.rule_id} has empty message"
            # A line is meaningless without its path.
            if diag.line is not None:
                assert diag.path is not None, f"Diagnostic {diag.rule_id} has line but no path"
