"""Ruff-style ``# noqa`` suppression, applied to a charm's YAML files.

charmlint mirrors ruff's directive syntax as closely as the YAML setting
allows:

- An inline ``# noqa`` comment suppresses every diagnostic reported on
  that line. ``# noqa: SECURITY-001, METADATA-002`` suppresses only the
  listed rules — matched by full rule ID (``SECURITY-001``) or by
  category (``SECURITY``), the same way ``select`` / ``ignore`` match.
- A file-level ``# charmlint: noqa`` (ruff's ``# ruff: noqa`` analogue),
  appearing on any line, suppresses the whole file. ``# charmlint: noqa:
  SECURITY-001`` suppresses only the listed rules across the file.

Diagnostics are line-anchored only when a rule records a line;
everything else anchors to the file, so it can still be silenced with a
file-level directive.

Like every comment-based linter directive, this is a line scan rather
than a full YAML parse: a ``#`` is treated as starting a comment only
when it is at the start of the line or preceded by whitespace, matching
YAML's own comment rule. A ``#`` embedded inside a quoted scalar can
still be misread, exactly as ruff's own tokeniser has edge cases.
"""

import dataclasses
import re

# ``# charmlint: noqa`` (file-level) must be tried before the bare inline
# form, since the latter's pattern also appears inside it.
_FILE_RE = re.compile(r"(?:^|\s)#\s*charmlint:\s*noqa(?::(?P<codes>[^#]*))?", re.IGNORECASE)
_INLINE_RE = re.compile(r"(?:^|\s)#\s*noqa(?::(?P<codes>[^#]*))?", re.IGNORECASE)

# A code is a category (``SECURITY``) or a full rule ID (``SECURITY-001``).
_CODE_RE = re.compile(r"^[A-Z]+(?:-[0-9]+)?$")


def _category_of(rule_id: str) -> str:
    """Return the category prefix of a rule ID (everything before ``-``)."""
    return rule_id.split("-", 1)[0]


def _parse_codes(raw: str | None) -> frozenset[str] | None:
    """Parse the codes after ``noqa:``.

    Returns ``None`` for a bare directive (no colon — suppress
    everything), or a frozenset of upper-cased codes. Tokens that do not
    look like a code are dropped, so a trailing free-text reason is
    harmless.
    """
    if raw is None:
        return None
    codes = {
        token.upper()
        for token in re.split(r"[,\s]+", raw.strip())
        if token and _CODE_RE.match(token.upper())
    }
    return frozenset(codes)


@dataclasses.dataclass(frozen=True)
class _Directive:
    """A parsed directive: bare (``codes is None``) or a set of codes."""

    codes: frozenset[str] | None

    def matches(self, rule_id: str) -> bool:
        """Whether this directive suppresses *rule_id*."""
        if self.codes is None:
            return True
        return rule_id in self.codes or _category_of(rule_id) in self.codes


@dataclasses.dataclass(frozen=True)
class FileNoqa:
    """The ``# noqa`` directives parsed out of a single YAML file."""

    file_level: tuple[_Directive, ...]
    by_line: dict[int, _Directive]

    def suppresses(self, rule_id: str, line: int | None) -> bool:
        """Whether *rule_id* on *line* (1-based, or ``None``) is silenced."""
        if any(d.matches(rule_id) for d in self.file_level):
            return True
        if line is not None:
            directive = self.by_line.get(line)
            if directive is not None and directive.matches(rule_id):
                return True
        return False


def parse(text: str) -> FileNoqa:
    """Parse all ``# noqa`` directives out of *text*."""
    file_level: list[_Directive] = []
    by_line: dict[int, _Directive] = {}
    for lineno, line in enumerate(text.splitlines(), start=1):
        file_match = _FILE_RE.search(line)
        if file_match is not None:
            file_level.append(_Directive(_parse_codes(file_match.group("codes"))))
            continue
        inline_match = _INLINE_RE.search(line)
        if inline_match is not None:
            by_line[lineno] = _Directive(_parse_codes(inline_match.group("codes")))
    return FileNoqa(file_level=tuple(file_level), by_line=by_line)
