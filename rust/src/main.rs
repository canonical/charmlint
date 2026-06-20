mod config;
mod context;
mod linter;
mod models;
mod rules;

use clap::Parser;
use std::path::PathBuf;

/// Lint a Juju charm for best practices, observability, testing, and more.
#[derive(Parser)]
#[command(name = "charmlint")]
#[command(about = "Lint a Juju charm for best practices, observability, testing, and more.")]
struct Cli {
    /// Path to the charm directory (default: current directory).
    #[arg(default_value = ".")]
    path: PathBuf,

    /// Output format.
    #[arg(long = "format", value_name = "FORMAT", default_value = "text")]
    output_format: String,

    /// Comma-separated list of rule categories to enable (e.g. COS,META).
    #[arg(long)]
    select: Option<String>,

    /// Comma-separated list of rule IDs or categories to skip.
    #[arg(long)]
    ignore: Option<String>,

    /// Minimum severity to report.
    #[arg(long)]
    severity: Option<String>,

    /// Path to .charmlint.yaml config file.
    #[arg(long)]
    config: Option<PathBuf>,

    /// Exit with code 2 if warnings are found.
    #[arg(long)]
    strict: bool,

    /// Disable coloured output.
    #[arg(long = "no-colour")]
    no_colour: bool,
}

// ANSI helpers.
const RESET: &str = "\x1b[0m";
const BOLD: &str = "\x1b[1m";
const DIM: &str = "\x1b[2m";
const RED: &str = "\x1b[1;31m";
const YELLOW: &str = "\x1b[1;33m";
const CYAN: &str = "\x1b[1;36m";
const GREEN: &str = "\x1b[1;32m";

fn severity_style(sev: models::Severity) -> &'static str {
    match sev {
        models::Severity::Error => RED,
        models::Severity::Warning => YELLOW,
        models::Severity::Info => CYAN,
    }
}

fn format_diagnostic_colour(
    d: &models::Diagnostic,
    charm_dir: &std::path::Path,
    use_colour: bool,
) -> String {
    let mut location = d.path.clone().unwrap_or_default();
    if let Some(p) = &d.path {
        if let Ok(rel) = std::path::Path::new(p).strip_prefix(charm_dir) {
            location = rel.to_string_lossy().to_string();
        }
    }
    if let Some(line) = d.line {
        location = format!("{location}:{line}");
    }

    if use_colour {
        let mut parts = Vec::new();
        if !location.is_empty() {
            parts.push(format!("{DIM}{location}{RESET}"));
        }
        parts.push(format!("{}{}{RESET}", severity_style(d.severity), d.rule_id));
        parts.push(d.message.clone());
        parts.join(" ")
    } else {
        d.format_text(Some(charm_dir))
    }
}

fn format_summary_colour(total: usize, errors: usize, warnings: usize, infos: usize, use_colour: bool) -> String {
    if total == 0 {
        return if use_colour {
            format!("{GREEN}No issues found.{RESET}")
        } else {
            "No issues found.".to_string()
        };
    }

    let mut pieces = Vec::new();
    if errors > 0 {
        let s = if errors == 1 { "" } else { "s" };
        let label = format!("{errors} error{s}");
        pieces.push(if use_colour {
            format!("{RED}{label}{RESET}")
        } else {
            label
        });
    }
    if warnings > 0 {
        let s = if warnings == 1 { "" } else { "s" };
        let label = format!("{warnings} warning{s}");
        pieces.push(if use_colour {
            format!("{YELLOW}{label}{RESET}")
        } else {
            label
        });
    }
    if infos > 0 {
        let label = format!("{infos} info");
        pieces.push(if use_colour {
            format!("{CYAN}{label}{RESET}")
        } else {
            label
        });
    }

    let s = if total == 1 { "" } else { "s" };
    let prefix = format!("Found {total} issue{s}");
    let prefix = if use_colour {
        format!("{BOLD}{prefix}{RESET}")
    } else {
        prefix
    };
    format!("{prefix} ({})", pieces.join(", "))
}

fn main() {
    let cli = Cli::parse();

    let charm_dir = cli.path.canonicalize().unwrap_or_else(|_| {
        eprintln!("Error: {} is not a directory", cli.path.display());
        std::process::exit(1);
    });

    if !charm_dir.is_dir() {
        eprintln!("Error: {} is not a directory", cli.path.display());
        std::process::exit(1);
    }

    // Determine colour mode.
    let use_colour =
        !cli.no_colour && atty_stdout() && cli.output_format != "json";

    // Load config.
    let mut lint_config =
        config::load_config(&charm_dir, cli.config.as_deref());

    // Overlay CLI flags.
    if let Some(select) = &cli.select {
        lint_config.select = select.split(',').map(|s| s.trim().to_string()).collect();
    }
    if let Some(ignore) = &cli.ignore {
        lint_config
            .ignore
            .extend(ignore.split(',').map(|s| s.trim().to_string()));
    }
    if let Some(severity) = &cli.severity {
        lint_config.min_severity = models::Severity::from_str_loose(severity);
    }

    let report = linter::lint(&charm_dir, &lint_config);

    if cli.output_format == "json" {
        println!(
            "{}",
            serde_json::to_string_pretty(&report).unwrap_or_default()
        );
    } else {
        for d in &report.diagnostics {
            println!("{}", format_diagnostic_colour(d, &charm_dir, use_colour));
        }
        if !report.diagnostics.is_empty() {
            println!();
        }
        println!(
            "{}",
            format_summary_colour(report.total, report.errors, report.warnings, report.info, use_colour)
        );
    }

    // Exit codes.
    if report.errors > 0 {
        std::process::exit(1);
    }
    if cli.strict && report.warnings > 0 {
        std::process::exit(2);
    }
}

fn atty_stdout() -> bool {
    #[cfg(unix)]
    {
        extern "C" {
            fn isatty(fd: i32) -> i32;
        }
        unsafe { isatty(1) != 0 }
    }
    #[cfg(not(unix))]
    {
        false
    }
}
