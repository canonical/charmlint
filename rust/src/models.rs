//! Core data models for charmlint.

use serde::Serialize;
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

/// Diagnostic severity level.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Severity {
    Error,
    Warning,
    Info,
}

impl Severity {
    pub fn from_str_loose(s: &str) -> Option<Self> {
        match s.to_lowercase().as_str() {
            "error" => Some(Self::Error),
            "warning" => Some(Self::Warning),
            "info" => Some(Self::Info),
            _ => None,
        }
    }

    pub fn label(&self) -> &'static str {
        match self {
            Self::Error => "error",
            Self::Warning => "warning",
            Self::Info => "info",
        }
    }

    /// Numeric order: Error=0, Warning=1, Info=2.
    pub fn order(&self) -> u8 {
        match self {
            Self::Error => 0,
            Self::Warning => 1,
            Self::Info => 2,
        }
    }
}

/// A single lint finding.
#[derive(Debug, Clone, Serialize)]
pub struct Diagnostic {
    pub rule_id: String,
    pub severity: Severity,
    pub message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub path: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub line: Option<usize>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub fix_hint: Option<String>,
}

impl Diagnostic {
    pub fn format_text(&self, charm_dir: Option<&Path>) -> String {
        let mut location = self.path.clone().unwrap_or_default();
        if let (Some(dir), Some(p)) = (charm_dir, &self.path) {
            if let Ok(rel) = Path::new(p).strip_prefix(dir) {
                location = rel.to_string_lossy().to_string();
            }
        }
        if let Some(line) = self.line {
            location = format!("{location}:{line}");
        }
        let prefix = if location.is_empty() {
            String::new()
        } else {
            format!("{location}: ")
        };
        format!("{prefix}{} {}", self.rule_id, self.message)
    }
}

/// All the data a rule needs, loaded once by the linter engine.
pub struct CharmContext {
    pub charm_dir: PathBuf,
    pub metadata: BTreeMap<String, serde_yaml::Value>,
    pub actions: BTreeMap<String, serde_yaml::Value>,
    pub config_options: BTreeMap<String, serde_yaml::Value>,
    pub python_files: Vec<PathBuf>,
    pub python_sources: BTreeMap<PathBuf, String>,
    pub readme_content: String,
    pub has_tests_unit: bool,
    pub has_tests_integration: bool,
}

/// Aggregated lint results.
#[derive(Debug, Serialize)]
pub struct LintReport {
    pub charm_dir: String,
    pub total: usize,
    pub errors: usize,
    pub warnings: usize,
    pub info: usize,
    pub diagnostics: Vec<Diagnostic>,
}

impl LintReport {
    pub fn new(charm_dir: &Path, diagnostics: Vec<Diagnostic>) -> Self {
        let errors = diagnostics
            .iter()
            .filter(|d| d.severity == Severity::Error)
            .count();
        let warnings = diagnostics
            .iter()
            .filter(|d| d.severity == Severity::Warning)
            .count();
        let info = diagnostics
            .iter()
            .filter(|d| d.severity == Severity::Info)
            .count();
        let total = diagnostics.len();
        Self {
            charm_dir: charm_dir.to_string_lossy().to_string(),
            total,
            errors,
            warnings,
            info,
            diagnostics,
        }
    }

    pub fn summary_line(&self) -> String {
        if self.total == 0 {
            return "No issues found.".to_string();
        }
        let mut parts = Vec::new();
        if self.errors > 0 {
            let s = if self.errors == 1 { "" } else { "s" };
            parts.push(format!("{} error{s}", self.errors));
        }
        if self.warnings > 0 {
            let s = if self.warnings == 1 { "" } else { "s" };
            parts.push(format!("{} warning{s}", self.warnings));
        }
        if self.info > 0 {
            parts.push(format!("{} info", self.info));
        }
        let s = if self.total == 1 { "" } else { "s" };
        format!("Found {} issue{s} ({})", self.total, parts.join(", "))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn diag(rule: &str, sev: Severity, msg: &str) -> Diagnostic {
        Diagnostic {
            rule_id: rule.to_string(),
            severity: sev,
            message: msg.to_string(),
            path: None,
            line: None,
            fix_hint: None,
        }
    }

    #[test]
    fn severity_from_str_loose_parses_known_values() {
        assert_eq!(Severity::from_str_loose("error"), Some(Severity::Error));
        assert_eq!(Severity::from_str_loose("Warning"), Some(Severity::Warning));
        assert_eq!(Severity::from_str_loose("INFO"), Some(Severity::Info));
    }

    #[test]
    fn severity_from_str_loose_rejects_unknown() {
        assert!(Severity::from_str_loose("critical").is_none());
        assert!(Severity::from_str_loose("").is_none());
    }

    #[test]
    fn severity_order_ranks_error_highest() {
        assert!(Severity::Error.order() < Severity::Warning.order());
        assert!(Severity::Warning.order() < Severity::Info.order());
    }

    #[test]
    fn severity_label_matches_external_names() {
        assert_eq!(Severity::Error.label(), "error");
        assert_eq!(Severity::Warning.label(), "warning");
        assert_eq!(Severity::Info.label(), "info");
    }

    #[test]
    fn diagnostic_format_text_basic() {
        let d = diag("COS001", Severity::Warning, "Missing tracing");
        assert_eq!(d.format_text(None), "COS001 Missing tracing");
    }

    #[test]
    fn diagnostic_format_text_with_path() {
        let d = Diagnostic {
            path: Some("src/charm.py".into()),
            ..diag("DEP001", Severity::Error, "StoredState")
        };
        assert_eq!(d.format_text(None), "src/charm.py: DEP001 StoredState");
    }

    #[test]
    fn diagnostic_format_text_with_path_and_line() {
        let d = Diagnostic {
            path: Some("src/charm.py".into()),
            line: Some(42),
            ..diag("DEP001", Severity::Error, "StoredState")
        };
        assert_eq!(d.format_text(None), "src/charm.py:42: DEP001 StoredState");
    }

    #[test]
    fn diagnostic_format_text_relative_to_charm_dir() {
        let d = Diagnostic {
            path: Some("/home/user/charm/src/charm.py".into()),
            ..diag("DEP001", Severity::Error, "StoredState")
        };
        let out = d.format_text(Some(Path::new("/home/user/charm")));
        assert_eq!(out, "src/charm.py: DEP001 StoredState");
    }

    #[test]
    fn diagnostic_serializes_with_omitted_optional_fields() {
        let d = diag("X", Severity::Info, "msg");
        let j = serde_json::to_value(&d).unwrap();
        assert_eq!(j["rule_id"], "X");
        assert_eq!(j["severity"], "info");
        assert!(j.get("path").is_none() || j["path"].is_null());
        assert!(j.get("line").is_none() || j["line"].is_null());
    }

    #[test]
    fn lint_report_empty_summary() {
        let report = LintReport::new(Path::new("/tmp/charm"), Vec::new());
        assert_eq!(report.total, 0);
        assert_eq!(report.errors, 0);
        assert_eq!(report.warnings, 0);
        assert_eq!(report.info, 0);
        assert_eq!(report.summary_line(), "No issues found.");
    }

    #[test]
    fn lint_report_counts_by_severity() {
        let diagnostics = vec![
            diag("E1", Severity::Error, "err1"),
            diag("E2", Severity::Error, "err2"),
            diag("W1", Severity::Warning, "warn1"),
            diag("I1", Severity::Info, "info1"),
        ];
        let report = LintReport::new(Path::new("/tmp/charm"), diagnostics);
        assert_eq!(report.total, 4);
        assert_eq!(report.errors, 2);
        assert_eq!(report.warnings, 1);
        assert_eq!(report.info, 1);
        let summary = report.summary_line();
        assert!(summary.contains("4 issues"), "got: {summary}");
        assert!(summary.contains("2 errors"), "got: {summary}");
    }

    #[test]
    fn lint_report_summary_singularises_one_of_each() {
        let diagnostics = vec![
            diag("E1", Severity::Error, "err"),
            diag("W1", Severity::Warning, "warn"),
        ];
        let report = LintReport::new(Path::new("/tmp/charm"), diagnostics);
        let summary = report.summary_line();
        assert!(summary.contains("1 error,"), "got: {summary}");
        assert!(summary.contains("1 warning"), "got: {summary}");
        assert!(!summary.contains("errors"));
    }
}
