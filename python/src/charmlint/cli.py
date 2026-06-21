"""Command-line interface for charmlint."""

import argparse
import contextlib
import json
import pathlib
import sys

from . import config as _config
from . import linter as _linter
from . import models

# ---------------------------------------------------------------------------
# ANSI colour helpers — disabled when stdout is not a terminal or --no-colour
# ---------------------------------------------------------------------------

_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"

_SEVERITY_STYLES: dict[models.Severity, str] = {
    models.Severity.ERROR: "\033[1;31m",  # bold red
    models.Severity.WARNING: "\033[1;33m",  # bold yellow
    models.Severity.INFO: "\033[1;36m",  # bold cyan
}

_use_colour = True


def _styled(text: str, style: str) -> str:
    """Wrap *text* in ANSI escape codes if colour is enabled."""
    if not _use_colour:
        return text
    return f"{style}{text}{_RESET}"


def _format_diagnostic_colour(d: models.Diagnostic, charm_dir: pathlib.Path) -> str:
    """Format a diagnostic with ANSI colours."""
    # Location (dim).
    location = d.path or ""
    if charm_dir and d.path:
        with contextlib.suppress(ValueError):
            location = str(pathlib.Path(d.path).relative_to(charm_dir))
    if d.line is not None:
        location = f"{location}:{d.line}"

    parts: list[str] = []
    if location:
        parts.append(_styled(location, _DIM))

    # Rule ID (severity colour).
    sev_style = _SEVERITY_STYLES.get(d.severity, "")
    parts.append(_styled(d.rule_id, sev_style))

    # Message (default text).
    parts.append(d.message)

    return " ".join(parts)


def _format_summary_colour(total: int, errors: int, warnings: int, infos: int) -> str:
    """Format the summary line with colours."""
    if total == 0:
        return _styled("No issues found.", "\033[1;32m")  # bold green

    pieces: list[str] = []
    if errors:
        label = f"{errors} error{'s' if errors != 1 else ''}"
        pieces.append(_styled(label, _SEVERITY_STYLES[models.Severity.ERROR]))
    if warnings:
        label = f"{warnings} warning{'s' if warnings != 1 else ''}"
        pieces.append(_styled(label, _SEVERITY_STYLES[models.Severity.WARNING]))
    if infos:
        label = f"{infos} info"
        pieces.append(_styled(label, _SEVERITY_STYLES[models.Severity.INFO]))

    return (
        _styled(f"Found {total} issue{'s' if total != 1 else ''}", _BOLD)
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
        "--format",
        choices=["text", "json"],
        default="text",
        dest="output_format",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--select",
        help="Comma-separated list of rule categories to enable (e.g. COS,META)",
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
        help="Path to .charmlint.yaml config file",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 2 if warnings are found (default: only errors cause non-zero exit)",
    )
    parser.add_argument(
        "--no-colour",
        action="store_true",
        help="Disable coloured output",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the charmlint CLI. Returns the exit code."""
    global _use_colour  # noqa: PLW0603

    parser = _build_parser()
    args = parser.parse_args(argv)

    # Determine colour mode: off if --no-colour, not a TTY, or JSON output.
    _use_colour = not args.no_colour and sys.stdout.isatty() and args.output_format != "json"

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
            print(_format_diagnostic_colour(diagnostic, charm_dir))
        if report.diagnostics:
            print()
        print(
            _format_summary_colour(
                len(report.diagnostics),
                report.error_count,
                report.warning_count,
                report.info_count,
            )
        )

    # Exit codes.
    if report.error_count > 0:
        return 1
    if args.strict and report.warning_count > 0:
        return 2
    return 0


def cli_entry() -> None:
    """Entry point for the ``charmlint`` console script."""
    sys.exit(main())
