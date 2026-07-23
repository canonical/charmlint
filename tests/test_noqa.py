"""Tests for ruff-style ``# noqa`` suppression on YAML files."""

import pathlib

import pytest

from charmlint import _noqa
from charmlint._linter import lint


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

    def test_noqa_case_insensitive(self, tmp_charm: pathlib.Path):
        _write(tmp_charm, _TWO_SECRETS.format(comment="  # NoQA: security-001"))
        assert _sec_options(tmp_charm) == {"api-token"}

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
        ("  security-001 ", frozenset({"SECURITY-001"})),
        ("SECURITY-001 because reasons", frozenset({"SECURITY-001", "BECAUSE", "REASONS"})),
    ],
)
def test_parse_codes(raw, codes):
    assert _noqa._parse_codes(raw) == codes
