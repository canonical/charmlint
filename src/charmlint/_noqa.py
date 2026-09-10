"""Ruff-style suppression comments, applied to a charm's YAML and Python files.

charmlint mirrors ruff's directive syntax as closely as the setting
allows. The preferred forms carry the tool name and bracket their codes,
as ruff's do since 0.16:

- ``# charmlint: ignore[SECURITY-001]`` suppresses the listed rules on
  one line. At the end of a line it covers that line; on a line of its
  own it covers the next line that is not blank or a comment, so a
  directive can sit above the thing it excuses.
- ``# charmlint: file-ignore[SECURITY-001]`` suppresses the listed rules
  across the whole file, wherever it appears.

Carrying the tool name matters in Python files, where a bare ``# noqa``
belongs to ruff: charmlint must neither eat ruff's directives nor make a
charm write a directive that ruff would then report as unused. So the
legacy bare forms are honoured in YAML only, where there is no other
linter to collide with:

- ``# noqa`` suppresses every diagnostic on that line, and ``# noqa:
  SECURITY-001, METADATA-002`` only the listed rules.
- ``# charmlint: noqa`` suppresses the whole file — the blanket
  file-level form, which ``file-ignore[...]`` has no spelling for, since
  its codes are required. ``# charmlint: noqa: SECURITY-001`` suppresses
  the listed rules across the file. Both are file-level wherever they
  appear, trailing a line included: position narrows ``ignore[...]``,
  but never the ``noqa`` forms that carry the tool name. Ruff is
  stricter — it takes ``# ruff: noqa`` as file-level only on a line of
  its own, and ignores one that trails code.

A code is a rule ID (``SECURITY-001``), a rule name
(``secret-in-plain-config``) or a category (``SECURITY``) — the same
spellings ``select`` and ``ignore`` accept, resolved by
:mod:`charmlint._selectors`. A code that names no rule silences nothing,
so a trailing free-text reason on a legacy ``# noqa:`` is harmless.

Diagnostics are line-anchored only when a rule records a line;
everything else anchors to the file, so it can still be silenced with a
file-level directive.

Like every comment-based linter directive, this is a line scan rather
than a full YAML or Python parse: a ``#`` is treated as starting a
comment only when it is at the start of the line or preceded by
whitespace, matching YAML's own comment rule. A ``#`` embedded inside a
quoted string can still be misread, exactly as ruff's own tokeniser has
edge cases.
"""

import dataclasses
import re

from . import _selectors

# The bracketed forms, spelled with the tool name. ``file-ignore`` must be
# tried before ``ignore``, since the latter's pattern also appears in it.
_FILE_IGNORE_RE = re.compile(r"(?:^|\s)#\s*charmlint:\s*file-ignore\[(?P<codes>[^\]]*)\]")
_IGNORE_RE = re.compile(r"(?:^|\s)#\s*charmlint:\s*ignore\[(?P<codes>[^\]]*)\]")

# The legacy bare forms, YAML-only. ``# charmlint: noqa`` (file-level)
# must be tried before the bare inline form, since the latter's pattern
# also appears inside it.
_LEGACY_FILE_RE = re.compile(r"(?:^|\s)#\s*charmlint:\s*noqa(?::(?P<codes>[^#]*))?", re.IGNORECASE)
_LEGACY_INLINE_RE = re.compile(r"(?:^|\s)#\s*noqa(?::(?P<codes>[^#]*))?", re.IGNORECASE)

# In a legacy bare directive the codes are not delimited, so anything
# that does not look like one is dropped and a trailing free-text reason
# is harmless. A code is a rule ID, a category, or a kebab-case name.
_CODE_RE = re.compile(r"^[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*$")


def _split_codes(raw: str) -> frozenset[str]:
    """Split a comma- or whitespace-separated code list."""
    return frozenset(token for token in re.split(r"[,\s]+", raw.strip()) if token)


def _parse_legacy_codes(raw: str | None) -> frozenset[str] | None:
    """Parse the codes after a legacy ``noqa:``.

    Returns ``None`` for a bare directive (no colon — suppress
    everything), or the frozenset of codes.
    """
    if raw is None:
        return None
    return frozenset(token for token in _split_codes(raw) if _CODE_RE.match(token))


@dataclasses.dataclass(frozen=True)
class _Directive:
    """A parsed directive: blanket (``codes is None``) or a set of codes."""

    codes: frozenset[str] | None

    def matches(self, rule_id: str) -> bool:
        """Whether this directive suppresses *rule_id*."""
        if self.codes is None:
            return True
        return any(rule_id in _selectors.resolve(code) for code in self.codes)


@dataclasses.dataclass(frozen=True)
class FileNoqa:
    """The suppression directives parsed out of a single file."""

    file_level: tuple[_Directive, ...]
    by_line: dict[int, tuple[_Directive, ...]]

    def suppresses(self, rule_id: str, line: int | None) -> bool:
        """Whether *rule_id* on *line* (1-based, or ``None``) is silenced."""
        if any(d.matches(rule_id) for d in self.file_level):
            return True
        if line is not None:
            return any(d.matches(rule_id) for d in self.by_line.get(line, ()))
        return False


def parse(text: str, *, legacy_noqa: bool = True) -> FileNoqa:
    """Parse all suppression directives out of *text*.

    *legacy_noqa* enables the bare ``# noqa`` forms, which are for YAML:
    in a Python file those comments are ruff's, not ours.
    """
    file_level: list[_Directive] = []
    by_line: dict[int, list[_Directive]] = {}
    # Own-line ``ignore[...]`` directives waiting for the line they cover.
    pending: list[_Directive] = []

    for lineno, line in enumerate(text.splitlines(), start=1):
        matched = _scan(line, lineno, legacy_noqa, file_level, by_line, pending)
        if not matched and pending and _is_code_line(line):
            by_line.setdefault(lineno, []).extend(pending)
            pending.clear()

    return FileNoqa(
        file_level=tuple(file_level),
        by_line={lineno: tuple(ds) for lineno, ds in by_line.items()},
    )


def _scan(
    line: str,
    lineno: int,
    legacy_noqa: bool,
    file_level: list[_Directive],
    by_line: dict[int, list[_Directive]],
    pending: list[_Directive],
) -> bool:
    """Record any directive on *line*, and report whether there was one.

    At most one directive is taken from a line, most specific spelling
    first, matching how ruff stops at the first directive it recognises.
    """
    file_ignore = _FILE_IGNORE_RE.search(line)
    if file_ignore is not None:
        file_level.append(_Directive(_split_codes(file_ignore.group("codes"))))
        return True

    ignore = _IGNORE_RE.search(line)
    if ignore is not None:
        directive = _Directive(_split_codes(ignore.group("codes")))
        if line[: ignore.start()].strip():
            # Trailing: it covers the line it is written on.
            by_line.setdefault(lineno, []).append(directive)
        else:
            # Own-line: it covers the next line with something on it.
            pending.append(directive)
        return True

    if not legacy_noqa:
        return False

    legacy_file = _LEGACY_FILE_RE.search(line)
    if legacy_file is not None:
        file_level.append(_Directive(_parse_legacy_codes(legacy_file.group("codes"))))
        return True

    legacy_inline = _LEGACY_INLINE_RE.search(line)
    if legacy_inline is not None:
        by_line.setdefault(lineno, []).append(
            _Directive(_parse_legacy_codes(legacy_inline.group("codes")))
        )
        return True

    return False


def _is_code_line(line: str) -> bool:
    """Whether *line* is something an own-line directive can cover.

    Blank lines and whole-line comments are skipped over, so directives
    stack and a comment may sit between one and the line it excuses.
    """
    stripped = line.strip()
    return bool(stripped) and not stripped.startswith("#")
