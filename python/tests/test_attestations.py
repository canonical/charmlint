"""Tests for ATT001/ATT002 attestation rules."""

import pathlib
from collections.abc import Iterator
from unittest import mock

import pytest

import pypi_attest
from charmlint import linter, models
from charmlint.rules import attestations as att_rules


@pytest.fixture(autouse=True)
def _reset_cache() -> Iterator[None]:
    pypi_attest.clear_cache()
    yield
    pypi_attest.clear_cache()


# ---------------------------------------------------------------------------
# _parse_requirement
# ---------------------------------------------------------------------------


class TestParseRequirement:
    def test_simple_name(self) -> None:
        assert att_rules._parse_requirement("ops") == ("ops", None)

    def test_name_with_lower_bound(self) -> None:
        # Lower bounds are not exact pins — treated as "latest" later.
        assert att_rules._parse_requirement("ops>=3.0") == ("ops", None)

    def test_exact_version(self) -> None:
        assert att_rules._parse_requirement("ops==3.7.0") == ("ops", "3.7.0")

    def test_ignores_comments_and_blanks(self) -> None:
        assert att_rules._parse_requirement("") is None
        assert att_rules._parse_requirement("   ") is None
        assert att_rules._parse_requirement("# just a comment") is None

    def test_ignores_pip_flags(self) -> None:
        assert att_rules._parse_requirement("-r other-requirements.txt") is None

    def test_strips_inline_comment(self) -> None:
        assert att_rules._parse_requirement("ops==3.7.0  # pin for ABC") == ("ops", "3.7.0")

    def test_handles_environment_markers(self) -> None:
        # PEP 508 markers are ignored; we only need the name (+ pin if present).
        parsed = att_rules._parse_requirement("ops==3.7.0; python_version >= '3.12'")
        assert parsed == ("ops", "3.7.0")


# ---------------------------------------------------------------------------
# _extract_dependencies
# ---------------------------------------------------------------------------


def _make_charm_with_deps(
    tmp_path: pathlib.Path,
    *,
    pyproject: str | None = None,
    requirements: str | None = None,
) -> pathlib.Path:
    """Create a charm dir with the given dependency files."""
    charm = tmp_path / "c"
    charm.mkdir()
    if pyproject is not None:
        (charm / "pyproject.toml").write_text(pyproject)
    if requirements is not None:
        (charm / "requirements.txt").write_text(requirements)
    return charm


class TestExtractDependencies:
    def test_reads_pyproject(self, tmp_path: pathlib.Path) -> None:
        charm = _make_charm_with_deps(
            tmp_path,
            pyproject=(
                "[project]\n"
                'name = "c"\nversion = "0.1"\n'
                'dependencies = ["ops>=3.0", "requests==2.33.0"]\n'
            ),
        )
        deps = att_rules._extract_dependencies(charm)
        names = [d[0] for d in deps]
        assert names == ["ops", "requests"]
        assert {d[0]: d[1] for d in deps} == {"ops": None, "requests": "2.33.0"}

    def test_reads_requirements_txt(self, tmp_path: pathlib.Path) -> None:
        charm = _make_charm_with_deps(
            tmp_path,
            requirements="ops==3.7.0\n# comment\njubilant\n",
        )
        deps = att_rules._extract_dependencies(charm)
        names = [d[0] for d in deps]
        assert names == ["ops", "jubilant"]

    def test_pyproject_wins_on_duplicates(self, tmp_path: pathlib.Path) -> None:
        """If a name appears in both files, pyproject's version info wins."""
        charm = _make_charm_with_deps(
            tmp_path,
            pyproject=('[project]\nname = "c"\nversion = "0.1"\ndependencies = ["ops==3.7.0"]\n'),
            requirements="ops\n",
        )
        deps = att_rules._extract_dependencies(charm)
        assert [(d[0], d[1]) for d in deps] == [("ops", "3.7.0")]

    def test_normalises_across_files(self, tmp_path: pathlib.Path) -> None:
        """``Ops`` in pyproject and ``ops`` in requirements are the same package."""
        charm = _make_charm_with_deps(
            tmp_path,
            pyproject=('[project]\nname = "c"\nversion = "0.1"\ndependencies = ["Ops>=3"]\n'),
            requirements="ops\n",
        )
        deps = att_rules._extract_dependencies(charm)
        assert len(deps) == 1


# ---------------------------------------------------------------------------
# Rule behaviour
# ---------------------------------------------------------------------------


def _provenance_stub(
    mapping: dict[str, pypi_attest.ProvenanceStatus],
) -> mock.MagicMock:
    """Patch target for ``pypi_attest.check_provenance`` that dispatches by name."""

    def _impl(
        name: str, version: str | None = None, **_kwargs: object
    ) -> pypi_attest.ProvenanceResult:
        normalised = pypi_attest.normalise_name(name)
        status = mapping.get(normalised, pypi_attest.ProvenanceStatus.ATTESTED)
        return pypi_attest.ProvenanceResult(
            name=normalised,
            status=status,
            version=version,
        )

    return mock.MagicMock(side_effect=_impl)


def _context(charm: pathlib.Path) -> models.CharmContext:
    (charm / "charmcraft.yaml").write_text("name: c\n")
    return linter.build_context(charm)


class TestATT001MustHave:
    def test_must_have_unattested_is_error(self, tmp_path: pathlib.Path) -> None:
        charm = _make_charm_with_deps(
            tmp_path,
            pyproject=('[project]\nname = "c"\nversion = "0.1"\ndependencies = ["ops>=3.0"]\n'),
        )
        context = _context(charm)
        rule = att_rules.MustHaveAttestationsMissing()

        stub = _provenance_stub({"ops": pypi_attest.ProvenanceStatus.UNATTESTED})
        with mock.patch("pypi_attest.check_provenance", stub):
            diags = rule.check(context)

        assert len(diags) == 1
        assert diags[0].rule_id == "ATT001"
        assert diags[0].severity is models.Severity.ERROR
        assert "ops" in diags[0].message

    def test_must_have_attested_is_silent(self, tmp_path: pathlib.Path) -> None:
        charm = _make_charm_with_deps(
            tmp_path,
            pyproject=(
                '[project]\nname = "c"\nversion = "0.1"\n'
                'dependencies = ["ops>=3.0", "ops-tracing"]\n'
            ),
        )
        context = _context(charm)
        rule = att_rules.MustHaveAttestationsMissing()

        stub = _provenance_stub({})  # Everything ATTESTED by default.
        with mock.patch("pypi_attest.check_provenance", stub):
            diags = rule.check(context)

        assert diags == []

    def test_unknown_status_does_not_fire(self, tmp_path: pathlib.Path) -> None:
        """Fail-open: network errors should not generate false positives."""
        charm = _make_charm_with_deps(
            tmp_path,
            pyproject=('[project]\nname = "c"\nversion = "0.1"\ndependencies = ["ops>=3.0"]\n'),
        )
        context = _context(charm)
        rule = att_rules.MustHaveAttestationsMissing()

        stub = _provenance_stub({"ops": pypi_attest.ProvenanceStatus.UNKNOWN})
        with mock.patch("pypi_attest.check_provenance", stub):
            diags = rule.check(context)

        assert diags == []

    def test_only_fires_for_must_have_names(self, tmp_path: pathlib.Path) -> None:
        """A non-must-have package is ATT002's job, not ATT001's."""
        charm = _make_charm_with_deps(
            tmp_path,
            pyproject=('[project]\nname = "c"\nversion = "0.1"\ndependencies = ["requests"]\n'),
        )
        context = _context(charm)
        rule = att_rules.MustHaveAttestationsMissing()

        stub = _provenance_stub({"requests": pypi_attest.ProvenanceStatus.UNATTESTED})
        with mock.patch("pypi_attest.check_provenance", stub):
            diags = rule.check(context)

        assert diags == []


class TestATT002OtherDeps:
    def test_non_must_have_unattested_is_info(self, tmp_path: pathlib.Path) -> None:
        charm = _make_charm_with_deps(
            tmp_path,
            pyproject=('[project]\nname = "c"\nversion = "0.1"\ndependencies = ["requests"]\n'),
        )
        context = _context(charm)
        rule = att_rules.DependencyMissingAttestation()

        stub = _provenance_stub({"requests": pypi_attest.ProvenanceStatus.UNATTESTED})
        with mock.patch("pypi_attest.check_provenance", stub):
            diags = rule.check(context)

        assert len(diags) == 1
        assert diags[0].rule_id == "ATT002"
        assert diags[0].severity is models.Severity.INFO

    def test_ignores_must_have_packages(self, tmp_path: pathlib.Path) -> None:
        """Must-have names are ATT001's responsibility."""
        charm = _make_charm_with_deps(
            tmp_path,
            pyproject=('[project]\nname = "c"\nversion = "0.1"\ndependencies = ["ops>=3.0"]\n'),
        )
        context = _context(charm)
        rule = att_rules.DependencyMissingAttestation()

        stub = _provenance_stub({"ops": pypi_attest.ProvenanceStatus.UNATTESTED})
        with mock.patch("pypi_attest.check_provenance", stub):
            diags = rule.check(context)

        assert diags == []

    def test_silent_when_all_attested(self, tmp_path: pathlib.Path) -> None:
        charm = _make_charm_with_deps(
            tmp_path,
            pyproject=(
                '[project]\nname = "c"\nversion = "0.1"\ndependencies = ["requests", "pydantic"]\n'
            ),
        )
        context = _context(charm)
        rule = att_rules.DependencyMissingAttestation()

        stub = _provenance_stub({})
        with mock.patch("pypi_attest.check_provenance", stub):
            diags = rule.check(context)

        assert diags == []
