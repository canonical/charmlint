"""Tests for security rules."""

import pathlib

import pytest

from charmlint._linter import lint
from charmlint._models import Severity
from tests.conftest import write_charm_source, write_charmcraft_yaml


def _write_charm(charm_dir: pathlib.Path, option: str) -> None:
    write_charmcraft_yaml(
        charm_dir,
        {
            "name": "test",
            "config": {"options": {option: {"type": "string", "description": "An option"}}},
        },
    )


class TestSecretInPlainConfig:
    """Tests for SECURITY-001 — secret-like config options."""

    @pytest.mark.parametrize(
        "option",
        ["password", "admin-password", "api_secret", "auth-token", "api-key", "db_credential"],
    )
    def test_secret_in_plain_config(self, tmp_charm: pathlib.Path, option: str):
        _write_charm(tmp_charm, option)
        report = lint(tmp_charm)
        diags = [d for d in list(report) if d.rule_id == "SECURITY-001"]
        assert len(diags) == 1
        assert diags[0].severity == Severity.ERROR
        assert option in diags[0].message

    @pytest.mark.parametrize("option", ["token-timeout", "password_rotation_days", "port"])
    def test_keyword_not_at_end_not_flagged(self, tmp_charm: pathlib.Path, option: str):
        _write_charm(tmp_charm, option)
        report = lint(tmp_charm)
        assert "SECURITY-001" not in {d.rule_id for d in list(report)}

    @pytest.mark.parametrize("option_type", ["secret", "boolean", "int", "float"])
    def test_non_string_option_not_flagged(self, tmp_charm: pathlib.Path, option_type: str):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "config": {"options": {"inject-password": {"type": option_type}}},
            },
        )
        report = lint(tmp_charm)
        assert "SECURITY-001" not in {d.rule_id for d in list(report)}

    def test_charm_using_juju_secrets_not_flagged(self, tmp_charm: pathlib.Path):
        _write_charm(tmp_charm, "admin-password")
        write_charm_source(
            tmp_charm,
            "import ops\n\n\ndef get(charm: ops.CharmBase) -> ops.Secret:\n"
            "    return charm.model.get_secret(label='admin')\n",
        )
        report = lint(tmp_charm)
        assert "SECURITY-001" not in {d.rule_id for d in list(report)}

    def test_secrets_use_in_vendored_lib_does_not_count(self, tmp_charm: pathlib.Path):
        _write_charm(tmp_charm, "admin-password")
        lib_dir = tmp_charm / "lib" / "charms" / "example" / "v0"
        lib_dir.mkdir(parents=True)
        (lib_dir / "example.py").write_text("def f(charm):\n    return charm.model.get_secret()\n")
        report = lint(tmp_charm)
        assert "SECURITY-001" in {d.rule_id for d in list(report)}

    def test_one_diagnostic_per_option(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(
            tmp_charm,
            {
                "name": "test",
                "config": {
                    "options": {
                        "admin-password": {"type": "string"},
                        "api-token": {"type": "string"},
                        "port": {"type": "int"},
                    }
                },
            },
        )
        report = lint(tmp_charm)
        diags = [d for d in list(report) if d.rule_id == "SECURITY-001"]
        assert len(diags) == 2
        assert all(d.path == "charmcraft.yaml" for d in diags)
