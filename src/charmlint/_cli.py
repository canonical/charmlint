"""Command-line interface for charmlint."""

import argparse
import json
import pathlib
import sys

from . import _config, _linter
from . import _models as models

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


def _styled(text: str, style: str, *, use_colour: bool) -> str:
    """Wrap *text* in ANSI escape codes if colour is enabled."""
    if use_colour and style:
        return f"{style}{text}{_RESET}"
    return text


def _format_diagnostic_colour(
    d: models.Diagnostic, charm_dir: pathlib.Path, *, use_colour: bool
) -> str:
    """Format a diagnostic with ANSI colours."""
    # Location (dim).
    location = d.path or ""
    if charm_dir and d.path:
        diag_path = pathlib.Path(d.path)
        if diag_path.is_relative_to(charm_dir):
            location = str(diag_path.relative_to(charm_dir))
    if d.line is not None:
        location = f"{location}:{d.line}"

    parts: list[str] = []
    if location:
        parts.append(_styled(location, _DIM, use_colour=use_colour))

    # Rule ID (severity colour).
    sev_style = _SEVERITY_STYLES.get(d.severity, "")
    parts.append(_styled(d.rule_id, sev_style, use_colour=use_colour))

    # Message (default text).
    parts.append(d.message)

    return " ".join(parts)


def _format_summary_colour(
    total: int, errors: int, warnings: int, infos: int, *, use_colour: bool
) -> str:
    """Format the summary line with colours."""
    if total == 0:
        return _styled("No issues found.", "\033[1;32m", use_colour=use_colour)  # bold green

    pieces: list[str] = []
    if errors:
        label = f"{errors} error{'s' if errors != 1 else ''}"
        pieces.append(
            _styled(label, _SEVERITY_STYLES[models.Severity.ERROR], use_colour=use_colour)
        )
    if warnings:
        label = f"{warnings} warning{'s' if warnings != 1 else ''}"
        pieces.append(
            _styled(label, _SEVERITY_STYLES[models.Severity.WARNING], use_colour=use_colour)
        )
    if infos:
        label = f"{infos} info"
        pieces.append(
            _styled(label, _SEVERITY_STYLES[models.Severity.INFO], use_colour=use_colour)
        )

    return (
        _styled(f"Found {total} issue{'s' if total != 1 else ''}", _BOLD, use_colour=use_colour)
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
        help=(
            "Comma-separated list of rule categories or IDs to enable "
            "(e.g. OBSERVABILITY,METADATA-001)"
        ),
    )
    parser.add_argument(
        "--ignore",
        help="Comma-separated list of rule IDs or categories to skip",
    )
    parser.add_argument(
        "--severity",
        choices=[s.value for s in models.Severity],
        help="Minimum severity to report",
    )
    parser.add_argument(
        "--config",
        help=(
            "Path to a TOML config file. If omitted, walks up from the charm "
            f"directory looking for {' or '.join(_config.STANDALONE_NAMES)}, or a "
            "[tool.charmlint] table in pyproject.toml."
        ),
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Exit with code 2 if warnings are found. Errors always exit "
            "with code 1 regardless of --strict."
        ),
    )
    parser.add_argument(
        "--no-colour",
        action="store_true",
        help="Disable coloured output",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print diagnostic details, including which config file was loaded",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the charmlint CLI. Returns the exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Determine colour mode: off if --no-colour, not a TTY, or JSON output.
    use_colour = not args.no_colour and sys.stdout.isatty() and args.output_format != "json"

    charm_dir = pathlib.Path(args.path).resolve()
    if not charm_dir.is_dir():
        print(f"Error: {args.path} is not a directory", file=sys.stderr)
        return 1

    # Load config from file, then overlay CLI flags.
    config_path = pathlib.Path(args.config) if args.config else None
    try:
        config = _config.load_config(charm_dir, config_path)
    except _config.ConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if args.verbose and config.source_path is not None:
        print(f"Loaded config from {config.source_path}", file=sys.stderr)

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
        any_diag = False
        for diagnostic in report:
            print(_format_diagnostic_colour(diagnostic, charm_dir, use_colour=use_colour))
            any_diag = True
        if any_diag:
            print()
        print(
            _format_summary_colour(
                len(report),
                report.error_count,
                report.warning_count,
                report.info_count,
                use_colour=use_colour,
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
