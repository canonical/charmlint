"""Tests for ruff-style suppression comments on YAML and Python files."""

import pathlib

import pytest

from charmlint import _noqa
from charmlint._linter import lint
from tests.conftest import write_charm_source, write_charmcraft_yaml


def _write(charm_dir: pathlib.Path, text: str, name: str = "charmcraft.yaml") -> None:
    (charm_dir / name).write_text(text)


def _sec_options(charm_dir: pathlib.Path) -> set[str]:
    """Return the config option names flagged by SECURITY-001."""
    return {d.message.split("'")[1] for d in lint(charm_dir) if d.rule_id == "SECURITY-001"}


_TWO_SECRETS = """\
name: test
config:
  options:
    admin-password:{comment}
      type: string
    api-token:
      type: string
"""


class TestInlineNoqa:
    """Inline ``# noqa`` on the config option's own line."""

    def test_bare_noqa_suppresses_that_option(self, tmp_charm: pathlib.Path):
        _write(tmp_charm, _TWO_SECRETS.format(comment="  # noqa"))
        assert _sec_options(tmp_charm) == {"api-token"}

    def test_rule_id_noqa_suppresses(self, tmp_charm: pathlib.Path):
        _write(tmp_charm, _TWO_SECRETS.format(comment="  # noqa: SECURITY-001"))
        assert _sec_options(tmp_charm) == {"api-token"}

    def test_category_noqa_suppresses(self, tmp_charm: pathlib.Path):
        _write(tmp_charm, _TWO_SECRETS.format(comment="  # noqa: SECURITY"))
        assert _sec_options(tmp_charm) == {"api-token"}

    def test_wrong_code_does_not_suppress(self, tmp_charm: pathlib.Path):
        _write(tmp_charm, _TWO_SECRETS.format(comment="  # noqa: METADATA-001"))
        assert _sec_options(tmp_charm) == {"admin-password", "api-token"}

    def test_keyword_is_case_insensitive(self, tmp_charm: pathlib.Path):
        _write(tmp_charm, _TWO_SECRETS.format(comment="  # NoQA: SECURITY-001"))
        assert _sec_options(tmp_charm) == {"api-token"}

    def test_codes_are_case_sensitive(self, tmp_charm: pathlib.Path):
        # The keyword may be spelled any way, but a code may not: an ID is
        # upper-case and a name lower-case, everywhere they are accepted.
        _write(tmp_charm, _TWO_SECRETS.format(comment="  # noqa: security-001"))
        assert _sec_options(tmp_charm) == {"admin-password", "api-token"}

    def test_trailing_reason_is_ignored(self, tmp_charm: pathlib.Path):
        _write(tmp_charm, _TWO_SECRETS.format(comment="  # noqa: SECURITY-001 legacy field"))
        assert _sec_options(tmp_charm) == {"api-token"}

    def test_multiple_codes(self, tmp_charm: pathlib.Path):
        _write(tmp_charm, _TWO_SECRETS.format(comment="  # noqa: METADATA-002, SECURITY-001"))
        assert _sec_options(tmp_charm) == {"api-token"}


class TestFileLevelNoqa:
    """File-level ``# charmlint: noqa`` anywhere in the file."""

    def test_bare_file_level_suppresses_all(self, tmp_charm: pathlib.Path):
        _write(tmp_charm, "# charmlint: noqa\n" + _TWO_SECRETS.format(comment=""))
        assert _sec_options(tmp_charm) == set()

    def test_file_level_rule_id(self, tmp_charm: pathlib.Path):
        _write(tmp_charm, "# charmlint: noqa: SECURITY-001\n" + _TWO_SECRETS.format(comment=""))
        assert _sec_options(tmp_charm) == set()

    def test_file_level_category(self, tmp_charm: pathlib.Path):
        _write(tmp_charm, "# charmlint: noqa: SECURITY\n" + _TWO_SECRETS.format(comment=""))
        assert _sec_options(tmp_charm) == set()

    def test_file_level_wrong_code_keeps_all(self, tmp_charm: pathlib.Path):
        _write(tmp_charm, "# charmlint: noqa: METADATA\n" + _TWO_SECRETS.format(comment=""))
        assert _sec_options(tmp_charm) == {"admin-password", "api-token"}

    def test_file_level_suppresses_rule_without_line(self, tmp_charm: pathlib.Path):
        # METADATA-001 (no-title) anchors to the file with no line, so it
        # can only be silenced file-wide.
        _write(tmp_charm, "name: test\n# charmlint: noqa: METADATA-001\n")
        rule_ids = {d.rule_id for d in lint(tmp_charm)}
        assert "METADATA-001" not in rule_ids


class TestNoqaScoping:
    """Directives only bite where they should."""

    def test_noqa_on_other_line_does_not_suppress(self, tmp_charm: pathlib.Path):
        # noqa on api-token's line must not silence admin-password.
        text = _TWO_SECRETS.format(comment="")
        text = text.replace("    api-token:", "    api-token:  # noqa: SECURITY-001")
        _write(tmp_charm, text)
        assert _sec_options(tmp_charm) == {"admin-password"}

    def test_noqa_in_config_yaml(self, tmp_charm: pathlib.Path):
        _write(tmp_charm, "name: test\n")
        _write(
            tmp_charm,
            "options:\n"
            "  admin-password:  # noqa: SECURITY-001\n"
            "    type: string\n"
            "  api-token:\n"
            "    type: string\n",
            name="config.yaml",
        )
        assert _sec_options(tmp_charm) == {"api-token"}


class TestParse:
    """Unit tests for the directive parser."""

    def test_bare_inline(self):
        parsed = _noqa.parse("admin-password:  # noqa\n")
        assert parsed.suppresses("SECURITY-001", line=1)
        assert parsed.suppresses("METADATA-002", line=1)

    def test_codes_inline(self):
        parsed = _noqa.parse("x:  # noqa: SECURITY-001\n")
        assert parsed.suppresses("SECURITY-001", line=1)
        assert not parsed.suppresses("METADATA-001", line=1)
        assert not parsed.suppresses("SECURITY-001", line=2)

    def test_hash_must_start_a_comment(self):
        # A '#' not preceded by whitespace is not a YAML comment.
        parsed = _noqa.parse('default: "a#noqa"\n')
        assert not parsed.suppresses("SECURITY-001", line=1)

    def test_file_level_takes_precedence_over_inline_shape(self):
        parsed = _noqa.parse("# charmlint: noqa: SECURITY\n")
        assert parsed.suppresses("SECURITY-001", line=99)
        assert not parsed.suppresses("METADATA-001", line=99)


@pytest.mark.parametrize(
    ("raw", "codes"),
    [
        (None, None),
        ("SECURITY-001", frozenset({"SECURITY-001"})),
        ("SECURITY-001, METADATA-002", frozenset({"SECURITY-001", "METADATA-002"})),
        ("  security-001 ", frozenset({"security-001"})),
        # Codes are kept as written and resolved later, so a free-text
        # reason survives parsing and simply never matches a rule.
        (
            "SECURITY-001 because reasons",
            frozenset({"SECURITY-001", "because", "reasons"}),
        ),
    ],
)
def test_parse_legacy_codes(raw, codes):
    assert _noqa._parse_legacy_codes(raw) == codes


class TestIgnoreComment:
    """The bracketed ``# charmlint: ignore[...]`` form on YAML."""

    def test_trailing_ignore_suppresses_that_line(self, tmp_charm: pathlib.Path):
        _write(tmp_charm, _TWO_SECRETS.format(comment="  # charmlint: ignore[SECURITY-001]"))
        assert _sec_options(tmp_charm) == {"api-token"}

    def test_rule_name_suppresses(self, tmp_charm: pathlib.Path):
        _write(
            tmp_charm,
            _TWO_SECRETS.format(comment="  # charmlint: ignore[secret-in-plain-config]"),
        )
        assert _sec_options(tmp_charm) == {"api-token"}

    def test_category_suppresses(self, tmp_charm: pathlib.Path):
        _write(tmp_charm, _TWO_SECRETS.format(comment="  # charmlint: ignore[SECURITY]"))
        assert _sec_options(tmp_charm) == {"api-token"}

    def test_wrong_code_does_not_suppress(self, tmp_charm: pathlib.Path):
        _write(tmp_charm, _TWO_SECRETS.format(comment="  # charmlint: ignore[METADATA-001]"))
        assert _sec_options(tmp_charm) == {"admin-password", "api-token"}

    def test_several_codes(self, tmp_charm: pathlib.Path):
        _write(
            tmp_charm,
            _TWO_SECRETS.format(comment="  # charmlint: ignore[METADATA-002, SECURITY-001]"),
        )
        assert _sec_options(tmp_charm) == {"api-token"}

    def test_trailing_reason_is_ignored(self, tmp_charm: pathlib.Path):
        _write(
            tmp_charm,
            _TWO_SECRETS.format(
                comment="  # charmlint: ignore[SECURITY-001]  # not really a password"
            ),
        )
        assert _sec_options(tmp_charm) == {"api-token"}

    def test_own_line_covers_the_next_line(self, tmp_charm: pathlib.Path):
        text = _TWO_SECRETS.format(comment="")
        text = text.replace(
            "    admin-password:",
            "    # charmlint: ignore[SECURITY-001]\n    admin-password:",
        )
        _write(tmp_charm, text)
        assert _sec_options(tmp_charm) == {"api-token"}

    def test_own_line_does_not_cover_further_lines(self, tmp_charm: pathlib.Path):
        # The directive covers admin-password only; api-token, two lines
        # further on, still reports.
        text = _TWO_SECRETS.format(comment="")
        text = text.replace(
            "    admin-password:",
            "    # charmlint: ignore[SECURITY]\n    admin-password:",
        )
        _write(tmp_charm, text)
        assert _sec_options(tmp_charm) == {"api-token"}

    def test_own_line_directives_stack(self, tmp_charm: pathlib.Path):
        text = _TWO_SECRETS.format(comment="")
        text = text.replace(
            "    admin-password:",
            "    # charmlint: ignore[METADATA-001]\n"
            "    # charmlint: ignore[SECURITY-001]\n"
            "    # a comment in between is fine\n"
            "    admin-password:",
        )
        _write(tmp_charm, text)
        assert _sec_options(tmp_charm) == {"api-token"}


class TestFileIgnoreComment:
    """The bracketed ``# charmlint: file-ignore[...]`` form."""

    def test_file_ignore_rule_id(self, tmp_charm: pathlib.Path):
        _write(
            tmp_charm,
            "# charmlint: file-ignore[SECURITY-001]\n" + _TWO_SECRETS.format(comment=""),
        )
        assert _sec_options(tmp_charm) == set()

    def test_file_ignore_rule_name(self, tmp_charm: pathlib.Path):
        _write(
            tmp_charm,
            "# charmlint: file-ignore[secret-in-plain-config]\n" + _TWO_SECRETS.format(comment=""),
        )
        assert _sec_options(tmp_charm) == set()

    def test_file_ignore_wrong_code_keeps_all(self, tmp_charm: pathlib.Path):
        _write(
            tmp_charm,
            "# charmlint: file-ignore[METADATA]\n" + _TWO_SECRETS.format(comment=""),
        )
        assert _sec_options(tmp_charm) == {"admin-password", "api-token"}

    def test_file_ignore_suppresses_rule_without_line(self, tmp_charm: pathlib.Path):
        # METADATA-001 anchors to the file with no line, so only a
        # file-level directive can silence it.
        _write(tmp_charm, "name: test\n# charmlint: file-ignore[missing-name]\n")
        assert "METADATA-001" not in {d.rule_id for d in lint(tmp_charm)}


_DEFER = """\
def handler(self, event):
    event.defer(){comment}
    self.do_more_work()
"""


def _correctness_hits(charm_dir: pathlib.Path) -> int:
    return len([d for d in lint(charm_dir) if d.rule_id == "CORRECTNESS-001"])


class TestPythonSuppression:
    """Python files honour the prefixed forms, and only those."""

    def test_no_directive_reports(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        write_charm_source(tmp_charm, _DEFER.format(comment=""))
        assert _correctness_hits(tmp_charm) == 1

    def test_trailing_ignore_suppresses(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        write_charm_source(
            tmp_charm, _DEFER.format(comment="  # charmlint: ignore[CORRECTNESS-001]")
        )
        assert _correctness_hits(tmp_charm) == 0

    def test_own_line_ignore_suppresses(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        write_charm_source(
            tmp_charm,
            "def handler(self, event):\n"
            "    # charmlint: ignore[defer-without-return]\n"
            "    event.defer()\n"
            "    self.do_more_work()\n",
        )
        assert _correctness_hits(tmp_charm) == 0

    def test_file_ignore_suppresses(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        write_charm_source(
            tmp_charm, "# charmlint: file-ignore[CORRECTNESS]\n" + _DEFER.format(comment="")
        )
        assert _correctness_hits(tmp_charm) == 0

    def test_bare_noqa_is_ruffs_and_does_not_suppress(self, tmp_charm: pathlib.Path):
        # A bare `noqa` comment in a Python file belongs to ruff;
        # charmlint must not eat it.
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        write_charm_source(tmp_charm, _DEFER.format(comment="  # noqa: CORRECTNESS-001"))
        assert _correctness_hits(tmp_charm) == 1

    def test_charmlint_noqa_is_not_honoured_in_python(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "x"})
        write_charm_source(tmp_charm, "# charmlint: noqa\n" + _DEFER.format(comment=""))
        assert _correctness_hits(tmp_charm) == 1
