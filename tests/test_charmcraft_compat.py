"""Tests for charmcraft-compatible rules."""

import pathlib

from charmlint._linter import lint
from charmlint._models import CharmContext, Severity
from charmlint._rules.charmcraft_compat import Entrypoint
from tests.conftest import write_charm_source, write_charmcraft_yaml


class TestDeprecatedSeries:
    """Tests for CHARMCRAFT-001 — deprecated 'series' attribute."""

    def test_series_present_is_warning(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test", "series": ["focal"]})
        report = lint(tmp_charm)
        diags = [d for d in list(report) if d.rule_id == "CHARMCRAFT-001"]
        assert len(diags) == 1
        assert diags[0].severity == Severity.WARNING
        assert diags[0].path == "charmcraft.yaml"

    def test_no_series(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        report = lint(tmp_charm)
        assert "CHARMCRAFT-001" not in {d.rule_id for d in list(report)}

    def test_series_in_legacy_metadata_yaml(self, tmp_charm: pathlib.Path):
        (tmp_charm / "metadata.yaml").write_text("name: test\nseries: [focal]\n")
        report = lint(tmp_charm)
        diags = [d for d in list(report) if d.rule_id == "CHARMCRAFT-001"]
        assert len(diags) == 1
        assert diags[0].path == "metadata.yaml"
        assert diags[0].line == 2

    def test_noqa_on_the_series_line_suppresses(self, tmp_charm: pathlib.Path):
        (tmp_charm / "charmcraft.yaml").write_text(
            "name: test\nseries:  # noqa: CHARMCRAFT-001\n  - focal\n"
        )
        report = lint(tmp_charm)
        assert "CHARMCRAFT-001" not in {d.rule_id for d in list(report)}

    def test_series_in_the_metadata_half_of_a_split_charm(self, tmp_charm: pathlib.Path):
        """series may sit in either file; the diagnostic must follow it."""
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        (tmp_charm / "metadata.yaml").write_text("summary: s\nseries:\n  - focal\n")
        report = lint(tmp_charm)
        diags = [d for d in list(report) if d.rule_id == "CHARMCRAFT-001"]
        assert len(diags) == 1
        assert diags[0].path == "metadata.yaml"
        assert diags[0].line == 2


class TestNamingConventions:
    """Tests for CHARMCRAFT-002 — hyphens vs underscores."""

    def test_underscore_config_option(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "config": {"options": {"my_option": {"type": "string"}}},
            },
        )
        report = lint(tmp_charm)
        diags = [d for d in list(report) if d.rule_id == "CHARMCRAFT-002"]
        assert len(diags) == 1
        assert diags[0].severity == Severity.WARNING
        assert "my_option" in diags[0].message
        assert "my-option" in diags[0].message
        assert diags[0].path == "charmcraft.yaml"

    def test_hyphenated_config_option_ok(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "config": {"options": {"my-option": {"type": "string"}}},
            },
        )
        report = lint(tmp_charm)
        assert "CHARMCRAFT-002" not in {d.rule_id for d in list(report)}

    def test_noqa_on_the_option_line_suppresses(self, tmp_charm: pathlib.Path):
        (tmp_charm / "charmcraft.yaml").write_text(
            "name: test\n"
            "config:\n"
            "  options:\n"
            "    my_option:  # noqa: CHARMCRAFT-002\n"
            "      type: string\n"
        )
        report = lint(tmp_charm)
        assert "CHARMCRAFT-002" not in {d.rule_id for d in list(report)}

    def test_noqa_in_legacy_config_yaml(self, tmp_charm: pathlib.Path):
        """Options may come from config.yaml, so the diagnostic must anchor there."""
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        (tmp_charm / "config.yaml").write_text(
            "options:\n  my_option:  # noqa: CHARMCRAFT-002\n    type: string\n"
        )
        report = lint(tmp_charm)
        assert "CHARMCRAFT-002" not in {d.rule_id for d in list(report)}

    def test_config_in_the_metadata_half_of_a_split_charm(self, tmp_charm: pathlib.Path):
        """A split charm may put its config block in metadata.yaml.

        The diagnostic must anchor to the file that actually declares the
        option, so its line number is meaningful and a ``noqa`` there works.
        """
        (tmp_charm / "charmcraft.yaml").write_text("name: test\ntype: charm\n")
        (tmp_charm / "metadata.yaml").write_text(
            "summary: s\nconfig:\n  options:\n    my_option:\n      type: string\n"
        )
        report = lint(tmp_charm)
        diags = [d for d in list(report) if d.rule_id == "CHARMCRAFT-002"]
        assert len(diags) == 1
        assert diags[0].path == "metadata.yaml"
        assert diags[0].line == 4

    def test_noqa_in_the_metadata_half_of_a_split_charm(self, tmp_charm: pathlib.Path):
        (tmp_charm / "charmcraft.yaml").write_text("name: test\ntype: charm\n")
        (tmp_charm / "metadata.yaml").write_text(
            "summary: s\nconfig:\n  options:\n"
            "    my_option:  # noqa: CHARMCRAFT-002\n      type: string\n"
        )
        report = lint(tmp_charm)
        assert "CHARMCRAFT-002" not in {d.rule_id for d in list(report)}

    def test_legacy_config_yaml_diagnostic_anchors_to_config_yaml(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        (tmp_charm / "config.yaml").write_text("options:\n  my_option:\n    type: string\n")
        report = lint(tmp_charm)
        diags = [d for d in list(report) if d.rule_id == "CHARMCRAFT-002"]
        assert len(diags) == 1
        assert diags[0].path == "config.yaml"
        assert diags[0].line == 2

    def test_empty_config_options_does_not_crash(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        (tmp_charm / "config.yaml").write_text("options:\n")
        report = lint(tmp_charm)
        assert "CHARMCRAFT-002" not in {d.rule_id for d in list(report)}
        assert "FATAL" not in {d.rule_id for d in list(report)}


def write_dispatch(charm_dir: pathlib.Path, exec_line: str = "exec ./src/charm.py") -> None:
    """Write a dispatch script that execs the given command."""
    (charm_dir / "dispatch").write_text(f"#!/bin/sh\n{exec_line}\n")


def write_entrypoint(charm_dir: pathlib.Path, executable: bool = True) -> None:
    """Write src/charm.py, optionally without the executable bit."""
    entrypoint = charm_dir / "src" / "charm.py"
    entrypoint.write_text("#!/usr/bin/env python3\n")
    entrypoint.chmod(0o755 if executable else 0o644)


class TestEntrypoint:
    """Tests for CHARMCRAFT-003 — entrypoint exists and is executable."""

    def test_missing_entrypoint(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_dispatch(tmp_charm)
        report = lint(tmp_charm)
        diags = [d for d in list(report) if d.rule_id == "CHARMCRAFT-003"]
        assert len(diags) == 1
        assert diags[0].severity == Severity.ERROR
        assert diags[0].path == "dispatch"
        assert "src/charm.py" in diags[0].message

    def test_entrypoint_not_executable(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_dispatch(tmp_charm)
        write_entrypoint(tmp_charm, executable=False)
        report = lint(tmp_charm)
        diags = [d for d in list(report) if d.rule_id == "CHARMCRAFT-003"]
        assert len(diags) == 1
        assert "not executable" in diags[0].message
        assert diags[0].path == "src/charm.py"
        assert diags[0].fix_hint == "Run: chmod +x src/charm.py"

    def test_entrypoint_is_a_directory(self, tmp_charm: pathlib.Path):
        # Driven through the rule directly: a directory named charm.py makes
        # the context loader emit FATAL before any rule runs.
        write_dispatch(tmp_charm)
        (tmp_charm / "src" / "charm.py").mkdir()
        diags = Entrypoint().check(CharmContext(charm_dir=tmp_charm))
        assert len(diags) == 1
        assert "not a regular file" in diags[0].message

    def test_executable_entrypoint_ok(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_dispatch(tmp_charm)
        write_entrypoint(tmp_charm)
        report = lint(tmp_charm)
        assert "CHARMCRAFT-003" not in {d.rule_id for d in list(report)}

    def test_charmcraft_generated_dispatch(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_dispatch(
            tmp_charm,
            'JUJU_DISPATCH_PATH="${JUJU_DISPATCH_PATH:-$0}" PYTHONPATH="lib:venv" '
            "exec ./src/charm.py",
        )
        write_entrypoint(tmp_charm, executable=False)
        report = lint(tmp_charm)
        diags = [d for d in list(report) if d.rule_id == "CHARMCRAFT-003"]
        assert len(diags) == 1
        assert diags[0].path == "src/charm.py"

    def test_explicit_interpreter_checks_the_script(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_dispatch(tmp_charm, "exec ./venv/bin/python3 ./src/charm.py")
        report = lint(tmp_charm)
        diags = [d for d in list(report) if d.rule_id == "CHARMCRAFT-003"]
        assert len(diags) == 1
        assert "src/charm.py" in diags[0].message

    def test_interpreted_entrypoint_needs_no_executable_bit(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_dispatch(tmp_charm, "exec /usr/bin/env python3 ./src/charm.py")
        write_entrypoint(tmp_charm, executable=False)
        report = lint(tmp_charm)
        assert "CHARMCRAFT-003" not in {d.rule_id for d in list(report)}

    def test_interpreter_invocation_without_exec(self, tmp_charm: pathlib.Path):
        # The pattern the slurm charms use: no exec, interpreter from a variable.
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_dispatch(
            tmp_charm,
            'JUJU_DISPATCH_PATH="${JUJU_DISPATCH_PATH:-$0}" PYTHONPATH=lib:venv '
            "$PYTHON_BIN ./src/charm.py",
        )
        report = lint(tmp_charm)
        diags = [d for d in list(report) if d.rule_id == "CHARMCRAFT-003"]
        assert len(diags) == 1
        assert "does not exist" in diags[0].message

    def test_no_dispatch(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        report = lint(tmp_charm)
        assert "CHARMCRAFT-003" not in {d.rule_id for d in list(report)}

    def test_dispatch_without_exec(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        (tmp_charm / "dispatch").write_text("#!/bin/sh\necho nothing to do\n")
        report = lint(tmp_charm)
        assert "CHARMCRAFT-003" not in {d.rule_id for d in list(report)}

    def test_unresolvable_entrypoints_are_skipped(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        for exec_line in (
            'exec "$JUJU_CHARM_DIR/src/charm.py"',
            "exec /usr/bin/true",
            "exec ../elsewhere/charm.py",
        ):
            write_dispatch(tmp_charm, exec_line)
            report = lint(tmp_charm)
            assert "CHARMCRAFT-003" not in {d.rule_id for d in list(report)}, exec_line


class TestUnknownTopLevelField:
    """Tests for CHARMCRAFT-004 — unrecognised top-level keys."""

    def test_known_fields_clean(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "type": "charm",
                "summary": "A test charm",
                "description": "Longer description.",
                "base": "ubuntu@24.04",
                "platforms": {"amd64": None},
                "parts": {"charm": {"plugin": "uv"}},
                "requires": {"db": {"interface": "postgresql"}},
                "provides": {"metrics": {"interface": "prometheus_scrape"}},
                "peers": {"cluster": {"interface": "cluster"}},
                "config": {"options": {"port": {"type": "int"}}},
                "actions": {"backup": {"description": "Run backup"}},
                "containers": {"app": {"resource": "app-image"}},
                "resources": {"app-image": {"type": "oci-image"}},
                "storage": {"data": {"type": "filesystem"}},
                "assumes": ["juju >= 3.1"],
                "subordinate": False,
                "charm-libs": [],
                "links": {"documentation": "https://example.com"},
                "extra-bindings": {"admin": {}},
            },
        )
        report = lint(tmp_charm)
        assert "CHARMCRAFT-004" not in {d.rule_id for d in list(report)}

    def test_typo_detected(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test", "sumary": "oops"})
        report = lint(tmp_charm)
        diags = [d for d in list(report) if d.rule_id == "CHARMCRAFT-004"]
        assert len(diags) == 1
        assert diags[0].severity == Severity.WARNING
        assert "sumary" in diags[0].message

    def test_typo_fix_hint(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test", "sumary": "oops"})
        report = lint(tmp_charm)
        diags = [d for d in list(report) if d.rule_id == "CHARMCRAFT-004"]
        assert diags[0].fix_hint is not None
        assert "summary" in diags[0].fix_hint

    def test_equally_close_candidates_are_all_suggested(self, tmp_charm: pathlib.Path):
        """'maintainere' is one edit from both 'maintainer' and 'maintainers'."""
        (tmp_charm / "metadata.yaml").write_text("name: test\nmaintainere: someone\n")
        report = lint(tmp_charm)
        diags = [d for d in list(report) if d.rule_id == "CHARMCRAFT-004"]
        assert len(diags) == 1
        assert diags[0].fix_hint == "Did you mean 'maintainer' or 'maintainers'?"

    def test_multiple_unknown(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "sumary": "oops",
                "descrption": "also oops",
            },
        )
        report = lint(tmp_charm)
        diags = [d for d in list(report) if d.rule_id == "CHARMCRAFT-004"]
        assert len(diags) == 2
        messages = " ".join(d.message for d in diags)
        assert "sumary" in messages
        assert "descrption" in messages

    def test_completely_unknown_no_hint(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test", "zzz-nonsense": "value"})
        report = lint(tmp_charm)
        diags = [d for d in list(report) if d.rule_id == "CHARMCRAFT-004"]
        assert len(diags) == 1
        assert diags[0].fix_hint is None

    def test_non_string_key_flagged_without_a_hint(self, tmp_charm: pathlib.Path):
        """An unquoted `on:` key parses to a bool under YAML 1.1, and must not crash."""
        (tmp_charm / "charmcraft.yaml").write_text("name: test\non: true\n")
        report = lint(tmp_charm)
        diags = [d for d in list(report) if d.rule_id == "CHARMCRAFT-004"]
        assert len(diags) == 1
        assert diags[0].fix_hint is None

    def test_legacy_fields_accepted(self, tmp_charm: pathlib.Path):
        """Legacy fields like 'series' and 'min-juju-version' are not unknown fields."""
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "series": ["focal"],
                "min-juju-version": "2.9",
            },
        )
        report = lint(tmp_charm)
        # CHARMCRAFT-001 fires for deprecated series, but CHARMCRAFT-004 must not.
        assert "CHARMCRAFT-004" not in {d.rule_id for d in list(report)}

    def test_path_is_charmcraft_yaml(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test", "sumary": "oops"})
        report = lint(tmp_charm)
        diags = [d for d in list(report) if d.rule_id == "CHARMCRAFT-004"]
        assert diags[0].path == "charmcraft.yaml"

    def test_path_is_metadata_yaml_for_legacy_charms(self, tmp_charm: pathlib.Path):
        (tmp_charm / "metadata.yaml").write_text("name: test\nsumary: oops\n")
        report = lint(tmp_charm)
        diags = [d for d in list(report) if d.rule_id == "CHARMCRAFT-004"]
        assert len(diags) == 1
        assert diags[0].path == "metadata.yaml"

    def test_metadata_yaml_specific_fields_not_flagged(self, tmp_charm: pathlib.Path):
        """Fields valid in metadata.yaml but not charmcraft.yaml must not be flagged."""
        (tmp_charm / "metadata.yaml").write_text(
            "name: test\n"
            "display-name: My Charm\n"
            "maintainers:\n  - foo@example.com\n"
            "docs: https://example.com/docs\n"
            "issues: https://example.com/issues\n"
            "source: https://example.com/source\n"
            "website: https://example.com\n"
        )
        report = lint(tmp_charm)
        assert "CHARMCRAFT-004" not in {d.rule_id for d in list(report)}

    def test_noqa_on_the_key_line_suppresses(self, tmp_charm: pathlib.Path):
        (tmp_charm / "charmcraft.yaml").write_text(
            "name: test\nvendor-thing: yes  # noqa: CHARMCRAFT-004\n"
        )
        report = lint(tmp_charm)
        assert "CHARMCRAFT-004" not in {d.rule_id for d in list(report)}

    def test_noqa_on_a_different_line_does_not_suppress(self, tmp_charm: pathlib.Path):
        (tmp_charm / "charmcraft.yaml").write_text(
            "name: test  # noqa: CHARMCRAFT-004\nvendor-thing: yes\n"
        )
        report = lint(tmp_charm)
        diags = [d for d in list(report) if d.rule_id == "CHARMCRAFT-004"]
        assert len(diags) == 1
        assert diags[0].line == 2

    def test_diagnostic_records_its_line(self, tmp_charm: pathlib.Path):
        (tmp_charm / "charmcraft.yaml").write_text("name: test\n\n# a comment\nsumary: oops\n")
        report = lint(tmp_charm)
        diags = [d for d in list(report) if d.rule_id == "CHARMCRAFT-004"]
        assert diags[0].line == 4

    def test_noqa_in_metadata_yaml_of_a_split_charm(self, tmp_charm: pathlib.Path):
        """The line has to come from the file that declared the key."""
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        (tmp_charm / "metadata.yaml").write_text(
            "summary: s\nvendor-thing: yes  # noqa: CHARMCRAFT-004\n"
        )
        report = lint(tmp_charm)
        assert "CHARMCRAFT-004" not in {d.rule_id for d in list(report)}

    def test_real_world_metadata_yaml_fields_not_flagged(self, tmp_charm: pathlib.Path):
        """Keys that are rare in the spec but common in published charms.

        Each of these appears in real charms and is valid; flagging them as
        typos would make the rule useless on any legacy charm.
        """
        (tmp_charm / "metadata.yaml").write_text(
            "name: test\n"
            "maintainer: Charmers <charmers@example.com>\n"
            "tags:\n  - misc\n"
            "categories:\n  - misc\n"
            "deployment:\n  type: stateful\n  service: cluster\n"
        )
        report = lint(tmp_charm)
        assert "CHARMCRAFT-004" not in {d.rule_id for d in list(report)}

    def test_charm_user_not_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test", "charm-user": "non-root"})
        report = lint(tmp_charm)
        assert "CHARMCRAFT-004" not in {d.rule_id for d in list(report)}

    def test_schema_only_charmcraft_fields_not_flagged(self, tmp_charm: pathlib.Path):
        """Keys in charmcraft's published schema that are rare in the wild.

        Absent from the corpus these tables were checked against, so they are
        pinned here to stop them regressing back into false positives.
        """
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "adopt-info": "my-part",
                "package-repositories": [{"type": "apt", "ppa": "example/ppa"}],
                "charmhub": {"api-url": "https://api.charmhub.io"},
            },
        )
        report = lint(tmp_charm)
        assert "CHARMCRAFT-004" not in {d.rule_id for d in list(report)}

    def test_split_metadata_keys_judged_against_their_own_file(self, tmp_charm: pathlib.Path):
        """A charm may split metadata across both files.

        The linter merges them, so each key has to be judged against the set
        for the file it actually came from — otherwise every split-metadata
        charm is flagged for its metadata.yaml-only keys.
        """
        write_charmcraft_yaml(tmp_charm, {"name": "test", "parts": {"charm": {"plugin": "uv"}}})
        (tmp_charm / "metadata.yaml").write_text(
            "display-name: My Charm\ntags:\n  - misc\nmaintainer: Charmers <c@example.com>\n"
        )
        report = lint(tmp_charm)
        assert "CHARMCRAFT-004" not in {d.rule_id for d in list(report)}

    def test_split_metadata_typo_anchors_to_the_right_file(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        (tmp_charm / "metadata.yaml").write_text("sumary: oops\n")
        report = lint(tmp_charm)
        diags = [d for d in list(report) if d.rule_id == "CHARMCRAFT-004"]
        assert len(diags) == 1
        assert diags[0].path == "metadata.yaml"
        assert "metadata.yaml" in diags[0].message

    def test_charmcraft_only_fields_flagged_in_metadata_yaml(self, tmp_charm: pathlib.Path):
        """charmcraft.yaml-only fields (parts, charm-libs, links) are flagged in metadata.yaml."""
        (tmp_charm / "metadata.yaml").write_text("name: test\nparts:\n  charm:\n    plugin: uv\n")
        report = lint(tmp_charm)
        diags = [d for d in list(report) if d.rule_id == "CHARMCRAFT-004"]
        assert len(diags) == 1
        assert "parts" in diags[0].message

    def test_metadata_yaml_fields_flagged_in_charmcraft_yaml(self, tmp_charm: pathlib.Path):
        """metadata.yaml-only fields (display-name, maintainers) are flagged in charmcraft.yaml."""
        write_charmcraft_yaml(tmp_charm, {"name": "test", "display-name": "My Charm"})
        report = lint(tmp_charm)
        diags = [d for d in list(report) if d.rule_id == "CHARMCRAFT-004"]
        assert len(diags) == 1
        assert diags[0].message == (
            "Field 'display-name' is valid in metadata.yaml but not charmcraft.yaml"
        )
        # A misplaced field is not a typo, so there is nothing to suggest.
        assert diags[0].fix_hint is None
        assert diags[0].path == "charmcraft.yaml"

    def test_maintainers_flagged_in_charmcraft_yaml(self, tmp_charm: pathlib.Path):
        """'maintainers' is valid in metadata.yaml but not charmcraft.yaml (use links.contact)."""
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "test", "maintainers": ["foo@example.com"]},
        )
        report = lint(tmp_charm)
        diags = [d for d in list(report) if d.rule_id == "CHARMCRAFT-004"]
        assert len(diags) == 1
        assert diags[0].message == (
            "Field 'maintainers' is valid in metadata.yaml but not charmcraft.yaml"
        )
        assert diags[0].fix_hint is None
        assert diags[0].path == "charmcraft.yaml"


class TestUnknownResourceField:
    """Tests for CHARMCRAFT-005 — unrecognised keys in resource definitions."""

    def test_valid_resource_fields(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "resources": {
                    "app-image": {
                        "type": "oci-image",
                        "description": "App image",
                    },
                    "tarball": {
                        "type": "file",
                        "filename": "app.tar.gz",
                        "description": "Source tarball",
                        "upstream-source": "https://example.com/app.tar.gz",
                    },
                },
            },
        )
        report = lint(tmp_charm)
        assert "CHARMCRAFT-005" not in {d.rule_id for d in list(report)}

    def test_typo_in_resource(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "resources": {
                    "app-image": {
                        "type": "oci-image",
                        "descrption": "App image",
                    },
                },
            },
        )
        report = lint(tmp_charm)
        diags = [d for d in list(report) if d.rule_id == "CHARMCRAFT-005"]
        assert len(diags) == 1
        assert diags[0].severity == Severity.WARNING
        assert "descrption" in diags[0].message
        assert "app-image" in diags[0].message

    def test_resource_fix_hint(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "resources": {
                    "img": {"type": "oci-image", "descrption": "typo"},
                },
            },
        )
        report = lint(tmp_charm)
        diags = [d for d in list(report) if d.rule_id == "CHARMCRAFT-005"]
        assert diags[0].fix_hint is not None
        assert "description" in diags[0].fix_hint

    def test_noqa_on_the_field_line_suppresses(self, tmp_charm: pathlib.Path):
        """A charm keeping a deliberate non-schema field can silence it in place.

        ``auto-fetch`` is the real-world case: a podspec-era convention that
        16 charms in the wild still carry.
        """
        (tmp_charm / "charmcraft.yaml").write_text(
            "name: test\n"
            "resources:\n"
            "  oci-image:\n"
            "    type: oci-image\n"
            "    auto-fetch: true  # noqa: CHARMCRAFT-005\n"
        )
        report = lint(tmp_charm)
        assert "CHARMCRAFT-005" not in {d.rule_id for d in list(report)}

    def test_noqa_on_a_different_line_does_not_suppress(self, tmp_charm: pathlib.Path):
        (tmp_charm / "charmcraft.yaml").write_text(
            "name: test\n"
            "resources:\n"
            "  oci-image:\n"
            "    type: oci-image  # noqa: CHARMCRAFT-005\n"
            "    auto-fetch: true\n"
        )
        report = lint(tmp_charm)
        diags = [d for d in list(report) if d.rule_id == "CHARMCRAFT-005"]
        assert len(diags) == 1
        assert diags[0].line == 5

    def test_resource_field_diagnostic_records_its_line(self, tmp_charm: pathlib.Path):
        (tmp_charm / "charmcraft.yaml").write_text(
            "name: test\nresources:\n  img:\n    type: oci-image\n    descrption: typo\n"
        )
        report = lint(tmp_charm)
        diags = [d for d in list(report) if d.rule_id == "CHARMCRAFT-005"]
        assert diags[0].line == 5
        assert diags[0].path == "charmcraft.yaml"

    def test_no_resources_section(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        report = lint(tmp_charm)
        assert "CHARMCRAFT-005" not in {d.rule_id for d in list(report)}

    def test_non_string_resource_key_flagged_without_a_hint(self, tmp_charm: pathlib.Path):
        (tmp_charm / "charmcraft.yaml").write_text(
            "name: test\nresources:\n  img:\n    type: oci-image\n    on: true\n"
        )
        report = lint(tmp_charm)
        diags = [d for d in list(report) if d.rule_id == "CHARMCRAFT-005"]
        assert len(diags) == 1
        assert diags[0].fix_hint is None

    def test_non_dict_resource_ignored(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "resources": {"img": "not-a-dict"},
            },
        )
        report = lint(tmp_charm)
        assert "CHARMCRAFT-005" not in {d.rule_id for d in list(report)}


class TestOpsMainCall:
    """Tests for CHARMCRAFT-006 — missing ops.main() call."""

    def test_no_ops_main_is_warning(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(tmp_charm, "import ops\n\n\nclass C(ops.CharmBase):\n    pass\n")
        report = lint(tmp_charm)
        diags = [d for d in list(report) if d.rule_id == "CHARMCRAFT-006"]
        assert len(diags) == 1
        assert diags[0].severity == Severity.WARNING
        assert diags[0].path == "src/charm.py"

    def test_ops_main_call(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            "import ops\n\n\nclass C(ops.CharmBase):\n    pass\n\n\nops.main(C)\n",
        )
        report = lint(tmp_charm)
        assert "CHARMCRAFT-006" not in {d.rule_id for d in list(report)}

    def test_legacy_main_import(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            "from ops.charm import CharmBase\nfrom ops.main import main\n\n\n"
            "class C(CharmBase):\n    pass\n\n\nmain(C)\n",
        )
        report = lint(tmp_charm)
        assert "CHARMCRAFT-006" not in {d.rule_id for d in list(report)}

    def test_aliased_import(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            "import ops as o\n\n\nclass C(o.CharmBase):\n    pass\n\n\no.main.main(C)\n",
        )
        report = lint(tmp_charm)
        assert "CHARMCRAFT-006" not in {d.rule_id for d in list(report)}

    def test_import_ops_main_submodule(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            "import ops.main\nfrom ops.charm import CharmBase\n\n\n"
            "class C(CharmBase):\n    pass\n\n\nops.main.main(C)\n",
        )
        report = lint(tmp_charm)
        assert "CHARMCRAFT-006" not in {d.rule_id for d in list(report)}

    def test_main_module_attribute_call(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            "from ops import CharmBase, main\n\n\nclass C(CharmBase):\n    pass\n\n\nmain.main(C)\n",
        )
        report = lint(tmp_charm)
        assert "CHARMCRAFT-006" not in {d.rule_id for d in list(report)}

    def test_main_in_another_src_module_still_flags(self, tmp_charm: pathlib.Path):
        # `ops.main()` only runs if it is in the file dispatch execs, so a
        # call in a sibling module doesn't make src/charm.py an entrypoint.
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(tmp_charm, "import ops\n\n\nclass C(ops.CharmBase):\n    pass\n")
        write_charm_source(
            tmp_charm,
            "import ops\n\nfrom charm import C\n\nops.main(C)\n",
            filename="entrypoint.py",
        )
        report = lint(tmp_charm)
        assert "CHARMCRAFT-006" in {d.rule_id for d in list(report)}

    def test_configured_entrypoint_is_used(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "parts": {"charm": {"charm-entrypoint": "src/entrypoint.py"}},
            },
        )
        write_charm_source(tmp_charm, "import ops\n\n\nclass C(ops.CharmBase):\n    pass\n")
        write_charm_source(
            tmp_charm,
            "import ops\n\nfrom charm import C\n\nops.main(C)\n",
            filename="entrypoint.py",
        )
        report = lint(tmp_charm)
        assert "CHARMCRAFT-006" not in {d.rule_id for d in list(report)}

    def test_configured_entrypoint_without_main_is_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "parts": {"charm": {"charm-entrypoint": "src/entrypoint.py"}},
            },
        )
        write_charm_source(
            tmp_charm,
            "import ops\n\n\nclass C(ops.CharmBase):\n    pass\n\n\nops.main(C)\n",
        )
        write_charm_source(tmp_charm, "import ops\n", filename="entrypoint.py")
        report = lint(tmp_charm)
        diags = [d for d in list(report) if d.rule_id == "CHARMCRAFT-006"]
        assert len(diags) == 1
        assert diags[0].path == "src/entrypoint.py"

    def test_non_python_entrypoint_is_skipped(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "parts": {"charm": {"charm-entrypoint": "scripts/entrypoint"}},
            },
        )
        write_charm_source(tmp_charm, "import ops\n\n\nclass C(ops.CharmBase):\n    pass\n")
        report = lint(tmp_charm)
        assert "CHARMCRAFT-006" not in {d.rule_id for d in list(report)}

    def test_missing_entrypoint_is_skipped(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        report = lint(tmp_charm)
        assert "CHARMCRAFT-006" not in {d.rule_id for d in list(report)}

    def test_malformed_parts_falls_back_to_default(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test", "parts": {"charm": ["bundle"]}})
        write_charm_source(tmp_charm, "import ops\n\n\nclass C(ops.CharmBase):\n    pass\n")
        report = lint(tmp_charm)
        assert "CHARMCRAFT-006" in {d.rule_id for d in list(report)}

    def test_non_ops_charm_is_skipped(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(tmp_charm, "import subprocess\n\n\ndef install():\n    pass\n")
        report = lint(tmp_charm)
        assert "CHARMCRAFT-006" not in {d.rule_id for d in list(report)}

    def test_ops_main_in_lib_does_not_count(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(tmp_charm, "import ops\n\n\nclass C(ops.CharmBase):\n    pass\n")
        lib_dir = tmp_charm / "lib" / "charms" / "example" / "v0"
        lib_dir.mkdir(parents=True)
        (lib_dir / "helper.py").write_text("import ops\n\nops.main(None)\n")
        report = lint(tmp_charm)
        assert "CHARMCRAFT-006" in {d.rule_id for d in list(report)}

    def test_relative_main_import_does_not_count(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(
            tmp_charm,
            "import ops\nfrom .helpers import main\n\n\nclass C(ops.CharmBase):\n    pass\n\n\nmain(C)\n",
        )
        report = lint(tmp_charm)
        assert "CHARMCRAFT-006" in {d.rule_id for d in list(report)}

    def test_syntax_error_source_is_skipped(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(tmp_charm, "import ops\n\ndef broken(:\n")
        report = lint(tmp_charm)
        assert "CHARMCRAFT-006" not in {d.rule_id for d in list(report)}


class TestLegacyBases:
    """Tests for CHARMCRAFT-007 — legacy 'bases' block."""

    def test_bases_present_is_info(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "test", "bases": [{"name": "ubuntu", "channel": "22.04"}]},
        )
        report = lint(tmp_charm)
        diags = [d for d in list(report) if d.rule_id == "CHARMCRAFT-007"]
        assert len(diags) == 1
        assert diags[0].severity == Severity.INFO
        assert diags[0].path == "charmcraft.yaml"

    def test_build_on_run_on_form_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "bases": [
                    {
                        "build-on": [{"name": "ubuntu", "channel": "22.04"}],
                        "run-on": [{"name": "ubuntu", "channel": "22.04"}],
                    }
                ],
            },
        )
        report = lint(tmp_charm)
        diags = [d for d in list(report) if d.rule_id == "CHARMCRAFT-007"]
        assert len(diags) == 1

    def test_base_and_platforms_not_flagged(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "base": "ubuntu@22.04",
                "platforms": {"amd64": None},
            },
        )
        report = lint(tmp_charm)
        assert "CHARMCRAFT-007" not in {d.rule_id for d in list(report)}

    def test_no_bases(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        report = lint(tmp_charm)
        assert "CHARMCRAFT-007" not in {d.rule_id for d in list(report)}

    def test_points_at_the_bases_line(self, tmp_charm: pathlib.Path):
        (tmp_charm / "charmcraft.yaml").write_text(
            "name: test\nsummary: s\nbases:\n  - name: ubuntu\n    channel: '22.04'\n"
        )
        report = lint(tmp_charm)
        diags = [d for d in list(report) if d.rule_id == "CHARMCRAFT-007"]
        assert len(diags) == 1
        assert diags[0].line == 3

    def test_noqa_on_the_bases_line_suppresses(self, tmp_charm: pathlib.Path):
        (tmp_charm / "charmcraft.yaml").write_text(
            "name: test\nbases:  # noqa: CHARMCRAFT-007\n  - name: ubuntu\n    channel: '22.04'\n"
        )
        report = lint(tmp_charm)
        assert "CHARMCRAFT-007" not in {d.rule_id for d in list(report)}

    def test_stale_bases_in_metadata_yaml_ignored(self, tmp_charm: pathlib.Path):
        """A leftover 'bases' in metadata.yaml is dead text charmcraft ignores."""
        write_charmcraft_yaml(
            tmp_charm,
            {"name": "test", "base": "ubuntu@24.04", "platforms": {"amd64": None}},
        )
        (tmp_charm / "metadata.yaml").write_text("summary: s\nbases:\n  - name: ubuntu\n")
        report = lint(tmp_charm)
        assert "CHARMCRAFT-007" not in {d.rule_id for d in list(report)}

    def test_bases_only_in_metadata_yaml_ignored(self, tmp_charm: pathlib.Path):
        (tmp_charm / "metadata.yaml").write_text("name: test\nbases:\n  - name: ubuntu\n")
        report = lint(tmp_charm)
        assert "CHARMCRAFT-007" not in {d.rule_id for d in list(report)}
