//! Core linter engine — loads context, runs rules, applies filters.

use crate::config::LintConfig;
use crate::context;
use crate::models::{Diagnostic, LintReport, Severity};
use crate::rules;
use std::path::Path;

/// Extract category from rule ID (strip trailing digits).
fn rule_category(rule_id: &str) -> String {
    rule_id.trim_end_matches(|c: char| c.is_ascii_digit()).to_string()
}

/// Check whether a rule should run given the config.
fn should_run_rule(rule_id: &str, config: &LintConfig) -> bool {
    let category = rule_category(rule_id);

    // Explicit disable via severity override.
    if config.severity_overrides.get(rule_id).map(|s| s.as_str()) == Some("off") {
        return false;
    }
    if config
        .severity_overrides
        .get(&category)
        .map(|s| s.as_str())
        == Some("off")
    {
        return false;
    }

    // If select is set, only run rules in those categories.
    if !config.select.is_empty() && !config.select.contains(&category) {
        return false;
    }

    // If ignore contains this specific rule or category, skip it.
    !config.ignore.contains(&rule_id.to_string()) && !config.ignore.contains(&category)
}

/// Resolve the effective severity for a rule, applying config overrides.
fn effective_severity(rule_id: &str, config: &LintConfig) -> Option<Severity> {
    if let Some(override_val) = config.severity_overrides.get(rule_id) {
        if override_val != "off" {
            return Severity::from_str_loose(override_val);
        }
    }
    None
}

/// Run all enabled rules against a charm directory.
pub fn lint(charm_dir: &Path, config: &LintConfig) -> LintReport {
    let ctx = context::build_context(charm_dir);

    if ctx.metadata.is_empty() {
        return LintReport::new(
            charm_dir,
            vec![Diagnostic {
                rule_id: "FATAL".to_string(),
                severity: Severity::Error,
                message:
                    "No charmcraft.yaml or metadata.yaml found — is this a charm directory?"
                        .to_string(),
                path: None,
                line: None,
                fix_hint: None,
            }],
        );
    }

    let all_diagnostics = rules::run_all(&ctx);

    // Filter and transform diagnostics.
    let mut filtered = Vec::new();
    for d in all_diagnostics {
        if !should_run_rule(&d.rule_id, config) {
            continue;
        }

        // Apply severity overrides.
        let d = if let Some(sev) = effective_severity(&d.rule_id, config) {
            Diagnostic {
                severity: sev,
                ..d
            }
        } else {
            d
        };

        // Filter by minimum severity.
        if let Some(min_sev) = &config.min_severity {
            if d.severity.order() > min_sev.order() {
                continue;
            }
        }

        filtered.push(d);
    }

    LintReport::new(charm_dir, filtered)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn write(path: &Path, contents: &str) {
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent).unwrap();
        }
        std::fs::write(path, contents).unwrap();
    }

    fn minimal_charm() -> tempfile::TempDir {
        let dir = tempfile::tempdir().unwrap();
        std::fs::create_dir(dir.path().join("src")).unwrap();
        write(&dir.path().join("charmcraft.yaml"), "name: test\n");
        dir
    }

    #[test]
    fn rule_category_strips_trailing_digits() {
        assert_eq!(rule_category("COS005"), "COS");
        assert_eq!(rule_category("META001"), "META");
        assert_eq!(rule_category("STR"), "STR");
    }

    #[test]
    fn should_run_rule_respects_off_override_for_specific_id() {
        let mut config = LintConfig::default();
        config
            .severity_overrides
            .insert("COS005".to_string(), "off".to_string());
        assert!(!should_run_rule("COS005", &config));
        assert!(should_run_rule("COS001", &config));
    }

    #[test]
    fn should_run_rule_respects_off_override_for_category() {
        let mut config = LintConfig::default();
        config
            .severity_overrides
            .insert("COS".to_string(), "off".to_string());
        assert!(!should_run_rule("COS005", &config));
        assert!(!should_run_rule("COS001", &config));
    }

    #[test]
    fn should_run_rule_with_select_only_runs_listed_categories() {
        let config = LintConfig {
            select: vec!["META".to_string()],
            ..LintConfig::default()
        };
        assert!(should_run_rule("META001", &config));
        assert!(!should_run_rule("COS005", &config));
    }

    #[test]
    fn should_run_rule_respects_ignore_list() {
        let config = LintConfig {
            ignore: vec!["STR003".to_string()],
            ..LintConfig::default()
        };
        assert!(!should_run_rule("STR003", &config));
        assert!(should_run_rule("STR001", &config));
    }

    #[test]
    fn effective_severity_resolves_from_override() {
        let mut config = LintConfig::default();
        config
            .severity_overrides
            .insert("COS001".to_string(), "error".to_string());
        assert_eq!(effective_severity("COS001", &config), Some(Severity::Error));
    }

    #[test]
    fn effective_severity_ignores_off() {
        let mut config = LintConfig::default();
        config
            .severity_overrides
            .insert("COS001".to_string(), "off".to_string());
        assert!(effective_severity("COS001", &config).is_none());
    }

    #[test]
    fn lint_returns_fatal_when_no_metadata_found() {
        let dir = tempfile::tempdir().unwrap();
        let report = lint(dir.path(), &LintConfig::default());
        assert_eq!(report.errors, 1);
        assert_eq!(report.diagnostics[0].rule_id, "FATAL");
    }

    #[test]
    fn lint_with_select_only_emits_selected_categories() {
        let dir = minimal_charm();
        let config = LintConfig {
            select: vec!["META".to_string()],
            ..LintConfig::default()
        };
        let report = lint(dir.path(), &config);
        for d in &report.diagnostics {
            assert!(d.rule_id.starts_with("META"), "unexpected rule {}", d.rule_id);
        }
    }

    #[test]
    fn lint_with_ignore_excludes_named_rule() {
        let dir = minimal_charm();
        let config = LintConfig {
            ignore: vec!["TEST001".to_string()],
            ..LintConfig::default()
        };
        let report = lint(dir.path(), &config);
        assert!(!report.diagnostics.iter().any(|d| d.rule_id == "TEST001"));
    }

    #[test]
    fn lint_severity_override_promotes_rule_to_error() {
        let dir = minimal_charm();
        let mut config = LintConfig::default();
        config
            .severity_overrides
            .insert("COS001".to_string(), "error".to_string());
        let report = lint(dir.path(), &config);
        let cos001: Vec<&Diagnostic> =
            report.diagnostics.iter().filter(|d| d.rule_id == "COS001").collect();
        assert!(!cos001.is_empty());
        assert_eq!(cos001[0].severity, Severity::Error);
    }

    #[test]
    fn lint_disable_via_off_removes_rule() {
        let dir = minimal_charm();
        let mut config = LintConfig::default();
        config
            .severity_overrides
            .insert("COS001".to_string(), "off".to_string());
        let report = lint(dir.path(), &config);
        assert!(!report.diagnostics.iter().any(|d| d.rule_id == "COS001"));
    }

    #[test]
    fn lint_min_severity_filters_lower_severities() {
        let dir = minimal_charm();
        let config = LintConfig {
            min_severity: Some(Severity::Error),
            ..LintConfig::default()
        };
        let report = lint(dir.path(), &config);
        for d in &report.diagnostics {
            assert_eq!(d.severity, Severity::Error, "rule {}", d.rule_id);
        }
    }
}
