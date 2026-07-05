"""Command-line interface for charmlint."""

import argparse
import importlib.metadata
import json
import os
import pathlib
import sys

from . import _config, _linter
from . import _models as models

# ---------------------------------------------------------------------------
# ANSI colour helpers
# ---------------------------------------------------------------------------

_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_GREEN = "\033[1;32m"

_SEVERITY_STYLES: dict[models.Severity, str] = {
    models.Severity.ERROR: "\033[1;31m",  # bold red
    models.Severity.WARNING: "\033[1;33m",  # bold yellow
    models.Severity.INFO: "\033[1;36m",  # bold cyan
}


def _style(text: str, style: str, colour: bool) -> str:
    """Wrap *text* in ANSI escape codes if *colour* is enabled."""
    if not colour:
        return text
    return f"{style}{text}{_RESET}"


def _colour_enabled(args: argparse.Namespace) -> bool:
    """Resolve colour mode: flag > NO_COLOR > FORCE_COLOR > TTY detection.

    ``NO_COLOR`` and ``FORCE_COLOR`` follow the informal convention of
    https://no-color.org/ — any non-empty value counts, and an explicit
    command-line flag beats both.
    """
    if args.no_colour or args.output_format == "json":
        return False
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return sys.stdout.isatty()


def _format_diagnostic(d: models.Diagnostic, charm_dir: pathlib.Path, *, colour: bool) -> str:
    """Format a diagnostic as a ruff-style single line, optionally coloured."""
    location = d.location(charm_dir)
    prefix = f"{_style(location, _DIM, colour)}: " if location else ""
    rule = _style(d.rule_id, _SEVERITY_STYLES.get(d.severity, ""), colour)
    return f"{prefix}{rule} {d.message}"


def _format_summary(report: models.LintReport, *, colour: bool) -> str:
    """Format the summary line, optionally coloured."""
    total = len(report.diagnostics)
    if total == 0:
        return _style("No issues found.", _GREEN, colour)

    pieces = [
        _style(label, _SEVERITY_STYLES[severity], colour)
        for severity, label in report.count_labels()
    ]
    return (
        _style(f"Found {total} issue{'s' if total != 1 else ''}", _BOLD, colour)
        + f" ({', '.join(pieces)})"
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="charmlint",
        description="Lint a Juju charm for best practices, observability, testing, and more.",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Path to the charm directory (default: current directory)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {importlib.metadata.version('charmlint')}",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        dest="output_format",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--select",
        help="Comma-separated list of rule categories or IDs to enable (e.g. COS,META001)",
    )
    parser.add_argument(
        "--ignore",
        help="Comma-separated list of rule IDs or categories to skip",
    )
    parser.add_argument(
        "--severity",
        choices=["error", "warning", "info"],
        help="Minimum severity to report",
    )
    parser.add_argument(
        "--config",
        help="Path to a TOML config file (pyproject.toml, charmlint.toml, or .charmlint.toml)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 2 if warnings are found (default: only errors cause non-zero exit)",
    )
    parser.add_argument(
        "--no-colour",
        "--no-color",
        action="store_true",
        help="Disable coloured output",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the charmlint CLI. Returns the exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    colour = _colour_enabled(args)

    charm_dir = pathlib.Path(args.path).resolve()
    if not charm_dir.is_dir():
        print(f"Error: {args.path} is not a directory", file=sys.stderr)
        return 1

    # Load config from file, then overlay CLI flags.
    config_path = pathlib.Path(args.config) if args.config else None
    config = _config.load_config(charm_dir, config_path)

    if args.select:
        config.select = [s.strip() for s in args.select.split(",")]
    if args.ignore:
        config.ignore.extend(s.strip() for s in args.ignore.split(","))
    if args.severity:
        config.min_severity = models.Severity(args.severity)

    report = _linter.lint(charm_dir, config)

    if args.output_format == "json":
        print(json.dumps(report.to_dict(), indent=2))
    else:
        for diagnostic in report.diagnostics:
            print(_format_diagnostic(diagnostic, charm_dir, colour=colour))
        if report.diagnostics:
            print()
        print(_format_summary(report, colour=colour))

    # Exit codes.
    if report.error_count > 0:
        return 1
    if args.strict and report.warning_count > 0:
        return 2
    return 0


def cli_entry() -> None:
    """Entry point for the ``charmlint`` console script."""
    sys.exit(main())
