//! End-to-end integration tests — drive the `charmlint` binary against
//! fixture charm directories and assert on the diagnostics reported.
//!
//! These mirror the shape of the Python `tests/unit/charmlint/test_linter.py`
//! suite but run the compiled binary with `--format json`, so they exercise
//! argument parsing, config overlay, and output formatting too.

use std::path::Path;
use std::process::Command;

fn charmlint_bin() -> &'static str {
    env!("CARGO_BIN_EXE_charmlint")
}

fn write(path: &Path, contents: &str) {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).unwrap();
    }
    std::fs::write(path, contents).unwrap();
}

/// Minimal charm with `name: test-charm` and a `src/` dir.
fn minimal_charm() -> tempfile::TempDir {
    let dir = tempfile::tempdir().unwrap();
    std::fs::create_dir(dir.path().join("src")).unwrap();
    write(&dir.path().join("charmcraft.yaml"), "name: test-charm\n");
    dir
}

fn run_json(charm_dir: &Path, extra_args: &[&str]) -> (std::process::ExitStatus, serde_json::Value) {
    let output = Command::new(charmlint_bin())
        .arg(charm_dir)
        .arg("--format")
        .arg("json")
        .args(extra_args)
        .output()
        .expect("run charmlint");
    let stdout = String::from_utf8_lossy(&output.stdout);
    let report: serde_json::Value =
        serde_json::from_str(&stdout).unwrap_or_else(|e| panic!("parse JSON: {e}: {stdout}"));
    (output.status, report)
}

fn rule_ids(report: &serde_json::Value) -> std::collections::BTreeSet<String> {
    report["diagnostics"]
        .as_array()
        .unwrap()
        .iter()
        .map(|d| d["rule_id"].as_str().unwrap().to_string())
        .collect()
}

#[test]
fn empty_directory_emits_fatal_diagnostic() {
    let dir = tempfile::tempdir().unwrap();
    let (status, report) = run_json(dir.path(), &[]);
    assert_eq!(report["errors"].as_u64(), Some(1));
    assert_eq!(rule_ids(&report), ["FATAL".to_string()].into_iter().collect());
    assert!(!status.success(), "expected non-zero exit for FATAL");
}

#[test]
fn minimal_charm_reports_meta_and_cos_diagnostics() {
    let dir = minimal_charm();
    let (_, report) = run_json(dir.path(), &[]);
    let ids = rule_ids(&report);
    // A bare `name: test` charm misses most observability and documentation
    // boxes — assert the rules we expect to fire.
    for expected in ["META002", "COS001", "COS002", "COS003", "COS004", "TEST001"] {
        assert!(ids.contains(expected), "missing {expected} in {ids:?}");
    }
}

#[test]
fn select_flag_filters_to_single_category() {
    let dir = minimal_charm();
    let (_, report) = run_json(dir.path(), &["--select", "META"]);
    let ids = rule_ids(&report);
    for id in &ids {
        assert!(id.starts_with("META"), "unexpected rule {id} passed --select META");
    }
    assert!(!ids.is_empty(), "expected at least one META diagnostic");
}

#[test]
fn ignore_flag_excludes_named_rule() {
    let dir = minimal_charm();
    let (_, report) = run_json(dir.path(), &["--ignore", "TEST001"]);
    let ids = rule_ids(&report);
    assert!(!ids.contains("TEST001"), "TEST001 should have been ignored");
}

#[test]
fn severity_flag_filters_to_errors_only() {
    let dir = minimal_charm();
    let (_, report) = run_json(dir.path(), &["--severity", "error"]);
    for d in report["diagnostics"].as_array().unwrap() {
        assert_eq!(
            d["severity"].as_str(),
            Some("error"),
            "non-error leaked through: {d}",
        );
    }
}

#[test]
fn config_file_severity_override_promotes_rule() {
    let dir = minimal_charm();
    write(
        &dir.path().join(".charmlint.yaml"),
        "rules:\n  COS001: error\n",
    );
    let (_, report) = run_json(dir.path(), &[]);
    let cos001: Vec<&serde_json::Value> = report["diagnostics"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|d| d["rule_id"].as_str() == Some("COS001"))
        .collect();
    assert_eq!(cos001.len(), 1);
    assert_eq!(cos001[0]["severity"].as_str(), Some("error"));
}

#[test]
fn strict_flag_produces_exit_code_two_for_warnings() {
    // Build a charm with no error-level rules firing but at least one warning
    // so `--strict` has only warnings to react to.
    let dir = minimal_charm();
    write(
        &dir.path().join("tests/unit/test_charm.py"),
        "def test_x(): pass\n",
    );
    let output = Command::new(charmlint_bin())
        .arg(dir.path())
        .arg("--strict")
        .arg("--no-colour")
        .output()
        .expect("run charmlint");
    assert_eq!(
        output.status.code(),
        Some(2),
        "expected exit 2 for warnings with --strict, got {:?} stderr={}",
        output.status.code(),
        String::from_utf8_lossy(&output.stderr),
    );
}

#[test]
fn nonexistent_path_exits_non_zero_with_stderr() {
    let output = Command::new(charmlint_bin())
        .arg("/definitely/does/not/exist/for-charmlint")
        .output()
        .expect("run charmlint");
    assert!(!output.status.success());
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(stderr.contains("not a directory"), "stderr: {stderr}");
}
