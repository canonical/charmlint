//! All charmlint rules — 40+ checks across 12 categories.

use crate::models::{CharmContext, Diagnostic, Severity};
use regex::Regex;
use serde_yaml::Value;
use std::collections::{BTreeMap, BTreeSet, HashSet};
use std::path::Path;
use walkdir::WalkDir;

// ── Helpers ──────────────────────────────────────────────────────────

fn diag(
    rule_id: &str,
    severity: Severity,
    message: &str,
    path: Option<&str>,
    line: Option<usize>,
    fix_hint: Option<&str>,
) -> Diagnostic {
    Diagnostic {
        rule_id: rule_id.to_string(),
        severity,
        message: message.to_string(),
        path: path.map(|s| s.to_string()),
        line,
        fix_hint: fix_hint.map(|s| s.to_string()),
    }
}

/// Collect all relation interface names from metadata.
fn all_relation_interfaces(metadata: &BTreeMap<String, Value>) -> HashSet<String> {
    let mut interfaces = HashSet::new();
    for section in &["requires", "provides", "peers"] {
        if let Some(Value::Mapping(rels)) = metadata.get(*section) {
            for (_name, rel_def) in rels {
                if let Value::Mapping(rd) = rel_def {
                    if let Some(Value::String(iface)) =
                        rd.get(Value::String("interface".into()))
                    {
                        interfaces.insert(iface.clone());
                    }
                }
            }
        }
    }
    interfaces
}

/// Concatenate all src/ Python source (not lib/).
fn src_content(ctx: &CharmContext) -> String {
    let mut parts = Vec::new();
    for (path, content) in &ctx.python_sources {
        if !path_has_lib(path) {
            parts.push(content.as_str());
        }
    }
    parts.join("\n")
}

fn path_has_lib(path: &Path) -> bool {
    path.components().any(|c| c.as_os_str() == "lib")
}

fn value_as_map(v: &Value) -> Option<&serde_yaml::Mapping> {
    v.as_mapping()
}

fn get_str(m: &serde_yaml::Mapping, key: &str) -> Option<String> {
    m.get(Value::String(key.into()))
        .and_then(|v| v.as_str())
        .map(|s| s.to_string())
}

// ── Rule runner ──────────────────────────────────────────────────────

/// Run all rules and return all diagnostics.
pub fn run_all(ctx: &CharmContext) -> Vec<Diagnostic> {
    let mut results = Vec::new();

    // META rules.
    results.extend(check_metadata(ctx));
    // COS rules.
    results.extend(check_cos(ctx));
    // TEST rules.
    results.extend(check_testing(ctx));
    // DEP rules.
    results.extend(check_deprecated(ctx));
    // ACT rules.
    results.extend(check_actions(ctx));
    // CFG rules.
    results.extend(check_config_quality(ctx));
    // SEC rules.
    results.extend(check_security(ctx));
    // STR rules.
    results.extend(check_structure(ctx));
    // DOC rules.
    results.extend(check_documentation(ctx));
    // LIB rules.
    results.extend(check_libraries(ctx));
    // CC rules.
    results.extend(check_charmcraft_compat(ctx));
    // STS rules.
    results.extend(check_status(ctx));

    results
}

// ── META (Metadata Fields) ───────────────────────────────────────────

fn check_metadata(ctx: &CharmContext) -> Vec<Diagnostic> {
    let checks: &[(&str, &str, &str, Severity)] = &[
        ("name", "META001", "Missing 'name' field in charm metadata", Severity::Error),
        ("display-name", "META002", "Missing 'display-name' field", Severity::Warning),
        ("summary", "META003", "Missing 'summary' field", Severity::Warning),
        ("description", "META004", "Missing 'description' field", Severity::Warning),
        ("docs", "META005", "Missing 'docs' URL", Severity::Info),
        ("issues", "META006", "Missing 'issues' URL", Severity::Info),
        ("source", "META007", "Missing 'source' URL", Severity::Info),
    ];

    let mut diagnostics = Vec::new();
    for &(field, rule_id, msg, severity) in checks {
        if ctx.metadata.get(field).is_none() {
            diagnostics.push(diag(rule_id, severity, msg, Some("charmcraft.yaml"), None, None));
        }
    }
    diagnostics
}

// ── COS (Observability) ──────────────────────────────────────────────

fn check_cos(ctx: &CharmContext) -> Vec<Diagnostic> {
    let interface_checks: &[(&str, &str, &str)] = &[
        ("tracing", "COS001", "Missing tracing relation (interface: tracing)"),
        (
            "prometheus_scrape",
            "COS002",
            "Missing metrics-endpoint relation (interface: prometheus_scrape)",
        ),
        (
            "loki_push_api",
            "COS003",
            "Missing logging relation (interface: loki_push_api)",
        ),
        (
            "grafana_dashboard",
            "COS004",
            "Missing grafana-dashboard relation (interface: grafana_dashboard)",
        ),
    ];

    let interfaces = all_relation_interfaces(&ctx.metadata);
    let mut diagnostics = Vec::new();

    for &(iface, rule_id, msg) in interface_checks {
        if !interfaces.contains(iface) {
            diagnostics.push(diag(
                rule_id,
                Severity::Warning,
                msg,
                Some("charmcraft.yaml"),
                None,
                None,
            ));
        }
    }

    // COS005: ops-tracing not installed.
    let mut found_tracing = false;
    for req_name in &["requirements.txt", "pyproject.toml"] {
        let req_path = ctx.charm_dir.join(req_name);
        if let Ok(content) = std::fs::read_to_string(&req_path) {
            if content.contains("ops-tracing") {
                found_tracing = true;
                break;
            }
        }
    }
    if !found_tracing {
        let re = Regex::new(r"ops_tracing|setup_tracing").unwrap();
        for content in ctx.python_sources.values() {
            if re.is_match(content) {
                found_tracing = true;
                break;
            }
        }
    }
    if !found_tracing {
        diagnostics.push(diag(
            "COS005",
            Severity::Warning,
            "ops-tracing not detected — add for distributed tracing",
            None,
            None,
            Some("Add 'ops-tracing' to requirements.txt or pyproject.toml"),
        ));
    }

    diagnostics
}

// ── TEST (Testing) ───────────────────────────────────────────────────

fn check_testing(ctx: &CharmContext) -> Vec<Diagnostic> {
    let mut diagnostics = Vec::new();

    if !ctx.has_tests_unit {
        diagnostics.push(diag(
            "TEST001",
            Severity::Error,
            "No unit tests found in tests/unit/",
            Some("tests/"),
            None,
            None,
        ));
    }

    if !ctx.has_tests_integration {
        diagnostics.push(diag(
            "TEST002",
            Severity::Warning,
            "No integration tests found in tests/integration/",
            Some("tests/"),
            None,
            None,
        ));
    }

    // TEST003: uses Harness.
    let test_dir = ctx.charm_dir.join("tests");
    if test_dir.is_dir() {
        let re = Regex::new(r"from\s+ops\.testing\s+import\s+Harness|Harness\s*\(").unwrap();
        for entry in WalkDir::new(&test_dir).follow_links(true) {
            if let Ok(e) = entry {
                if e.file_type().is_file()
                    && e.path().extension().map_or(false, |ext| ext == "py")
                {
                    if let Ok(content) = std::fs::read_to_string(e.path()) {
                        if re.is_match(&content) {
                            diagnostics.push(diag(
                                "TEST003",
                                Severity::Error,
                                "Uses deprecated Harness — migrate to Scenario (ops.testing)",
                                Some(&e.path().to_string_lossy()),
                                None,
                                Some("Use ops.testing.Context and State instead of Harness"),
                            ));
                            break;
                        }
                    }
                }
            }
        }
    }

    diagnostics
}

// ── DEP (Deprecated APIs) ────────────────────────────────────────────

fn check_deprecated(ctx: &CharmContext) -> Vec<Diagnostic> {
    let checks: &[(&str, &str, &str, &str)] = &[
        (
            r"\bStoredState\b",
            "DEP001",
            "Uses deprecated StoredState",
            "Use instance attributes or Juju secrets instead",
        ),
        (
            r"\bfrom\s+ops\.testing\s+import\s+Harness\b",
            "DEP002",
            "Imports deprecated Harness from ops.testing",
            "Use Scenario (ops.testing.Context, State) instead",
        ),
        (
            r"\bself\.framework\.breakpoint\b",
            "DEP003",
            "Uses removed framework.breakpoint()",
            "Use standard Python breakpoint() or debugger",
        ),
    ];

    let mut diagnostics = Vec::new();
    for &(pattern, rule_id, msg, fix) in checks {
        let re = Regex::new(pattern).unwrap();
        let mut found = false;
        for (path, content) in &ctx.python_sources {
            if path_has_lib(path) {
                continue;
            }
            for (i, line) in content.lines().enumerate() {
                if re.is_match(line) {
                    diagnostics.push(diag(
                        rule_id,
                        Severity::Error,
                        msg,
                        Some(&path.to_string_lossy()),
                        Some(i + 1),
                        Some(fix),
                    ));
                    found = true;
                    break;
                }
            }
            if found {
                break;
            }
        }
    }
    diagnostics
}

// ── ACT (Actions) ────────────────────────────────────────────────────

fn check_actions(ctx: &CharmContext) -> Vec<Diagnostic> {
    let expected: &[(&str, &str, &[&str])] = &[
        (
            "ACT001",
            "get-health",
            &["health-check", "check-health", "get-status", "health"],
        ),
        ("ACT002", "pause", &["stop", "disable"]),
        ("ACT003", "resume", &["start", "enable"]),
    ];

    let action_names: BTreeSet<&str> = ctx.actions.keys().map(|s| s.as_str()).collect();
    let mut diagnostics = Vec::new();

    for &(rule_id, canonical, aliases) in expected {
        let mut found = action_names.contains(canonical);
        if !found {
            for alias in aliases {
                if action_names.contains(alias) {
                    found = true;
                    break;
                }
            }
        }
        if !found {
            let alias_str = aliases.join(", ");
            diagnostics.push(diag(
                rule_id,
                Severity::Warning,
                &format!("Missing '{canonical}' action (or alias: {alias_str})"),
                Some("charmcraft.yaml"),
                None,
                Some(&format!("Add a '{canonical}' action to charmcraft.yaml")),
            ));
        }
    }

    // ACT004: action missing description.
    for (action_name, action_def) in &ctx.actions {
        if let Some(m) = value_as_map(action_def) {
            if get_str(m, "description").is_none() {
                diagnostics.push(diag(
                    "ACT004",
                    Severity::Warning,
                    &format!("Action '{action_name}' is missing a description"),
                    Some("charmcraft.yaml"),
                    None,
                    None,
                ));
            }
        }
    }

    // ACT005: action param missing description.
    for (action_name, action_def) in &ctx.actions {
        if let Some(m) = value_as_map(action_def) {
            let params = m
                .get(Value::String("params".into()))
                .or_else(|| m.get(Value::String("parameters".into())));
            if let Some(params_val) = params {
                if let Some(params_map) = value_as_map(params_val) {
                    let properties = params_map
                        .get(Value::String("properties".into()))
                        .and_then(|v| value_as_map(v))
                        .unwrap_or(params_map);
                    for (param_key, param_val) in properties {
                        if let (Value::String(param_name), Some(pd)) =
                            (param_key, value_as_map(param_val))
                        {
                            if get_str(pd, "description").is_none() {
                                diagnostics.push(diag(
                                    "ACT005",
                                    Severity::Info,
                                    &format!(
                                        "Action '{action_name}' parameter '{param_name}' is missing a description"
                                    ),
                                    Some("charmcraft.yaml"),
                                    None,
                                    None,
                                ));
                            }
                        }
                    }
                }
            }
        }
    }

    diagnostics
}

// ── CFG (Config Quality) ─────────────────────────────────────────────

fn check_config_quality(ctx: &CharmContext) -> Vec<Diagnostic> {
    let mut diagnostics = Vec::new();
    for (opt_name, opt_def) in &ctx.config_options {
        if let Some(m) = value_as_map(opt_def) {
            if get_str(m, "type").is_none() {
                diagnostics.push(diag(
                    "CFG001",
                    Severity::Warning,
                    &format!("Config option '{opt_name}' is missing a type"),
                    Some("charmcraft.yaml"),
                    None,
                    None,
                ));
            }
            if !m.contains_key(Value::String("default".into())) {
                diagnostics.push(diag(
                    "CFG002",
                    Severity::Info,
                    &format!("Config option '{opt_name}' is missing a default value"),
                    Some("charmcraft.yaml"),
                    None,
                    None,
                ));
            }
            if get_str(m, "description").is_none() {
                diagnostics.push(diag(
                    "CFG003",
                    Severity::Warning,
                    &format!("Config option '{opt_name}' is missing a description"),
                    Some("charmcraft.yaml"),
                    None,
                    None,
                ));
            }
        }
    }
    diagnostics
}

// ── SEC (Security) ───────────────────────────────────────────────────

fn check_security(ctx: &CharmContext) -> Vec<Diagnostic> {
    let secret_keywords = ["password", "secret", "token", "api-key", "api_key", "credential"];

    // SEC001: secret in plain config.
    let all_source = src_content(ctx);
    let has_juju_secrets = Regex::new(r"juju.*secret|Secret(?:Changed|Rotate)")
        .unwrap()
        .is_match(&all_source);

    let secret_opts: Vec<&str> = ctx
        .config_options
        .keys()
        .filter(|name| {
            let lower = name.to_lowercase();
            secret_keywords.iter().any(|kw| lower.contains(kw))
        })
        .map(|s| s.as_str())
        .collect();

    let mut diagnostics = Vec::new();
    if !secret_opts.is_empty() && !has_juju_secrets {
        for opt in secret_opts {
            diagnostics.push(diag(
                "SEC001",
                Severity::Error,
                &format!(
                    "Config option '{opt}' looks like a secret — use Juju secrets instead of plain-text config"
                ),
                Some("charmcraft.yaml"),
                None,
                Some("Use the Juju secrets API for sensitive data"),
            ));
        }
    }

    // SEC002: no TLS support.
    let mut has_tls = false;
    for section in &["requires", "provides", "peers"] {
        if let Some(Value::Mapping(rels)) = ctx.metadata.get(*section) {
            for (_name, rel_def) in rels {
                if let Value::Mapping(rd) = rel_def {
                    if let Some(Value::String(iface)) =
                        rd.get(Value::String("interface".into()))
                    {
                        if iface == "tls-certificates" || iface == "certificates" {
                            has_tls = true;
                        }
                    }
                }
            }
        }
    }
    if !has_tls {
        let all_src = ctx
            .python_sources
            .values()
            .cloned()
            .collect::<Vec<_>>()
            .join("\n");
        let re = Regex::new(r"(?i)\btls\b|\bcertificate\b|\bssl\b").unwrap();
        if re.is_match(&all_src) {
            has_tls = true;
        }
    }
    if !has_tls {
        diagnostics.push(diag(
            "SEC002",
            Severity::Info,
            "No TLS/encryption support detected",
            None,
            None,
            Some("Add a tls-certificates relation for encryption in transit"),
        ));
    }

    diagnostics
}

// ── STR (Structure) ──────────────────────────────────────────────────

fn check_structure(ctx: &CharmContext) -> Vec<Diagnostic> {
    let mut diagnostics = Vec::new();

    // STR001: no licence.
    if !ctx.charm_dir.join("LICENSE").exists() && !ctx.charm_dir.join("LICENCE").exists() {
        diagnostics.push(diag(
            "STR001",
            Severity::Info,
            "No LICENSE/LICENCE file found",
            None,
            None,
            None,
        ));
    }

    // STR002: no icon.
    if !ctx.charm_dir.join("icon.svg").exists() {
        diagnostics.push(diag(
            "STR002",
            Severity::Info,
            "No icon.svg found",
            None,
            None,
            None,
        ));
    }

    // STR003: no type annotations.
    let re = Regex::new(r"def\s+\w+\([^)]*\)\s*->").unwrap();
    let mut has_annotations = false;
    for (path, content) in &ctx.python_sources {
        if path_has_lib(path) {
            continue;
        }
        if re.is_match(content) {
            has_annotations = true;
            break;
        }
    }
    if !has_annotations {
        diagnostics.push(diag(
            "STR003",
            Severity::Info,
            "No type annotations found — add return-type hints to functions",
            None,
            None,
            Some("Add -> ReturnType annotations to function definitions"),
        ));
    }

    diagnostics
}

// ── DOC (Documentation) ──────────────────────────────────────────────

fn check_documentation(ctx: &CharmContext) -> Vec<Diagnostic> {
    let mut diagnostics = Vec::new();

    // DOC001: no README.
    if !ctx.charm_dir.join("README.md").exists() {
        diagnostics.push(diag(
            "DOC001",
            Severity::Warning,
            "No README.md found",
            None,
            None,
            None,
        ));
    }

    // DOC002-DOC005: topic checks.
    let topic_checks: &[(&str, &str, &str)] = &[
        ("installation", "DOC002", "No installation/setup documentation found"),
        ("configuration", "DOC003", "No configuration documentation found"),
        ("usage", "DOC004", "No usage documentation found"),
        ("troubleshooting", "DOC005", "No troubleshooting documentation found"),
    ];

    for &(keyword, rule_id, msg) in topic_checks {
        let severity = if rule_id == "DOC002" {
            Severity::Warning
        } else {
            Severity::Info
        };
        if !check_doc_topic(ctx, keyword) {
            diagnostics.push(diag(rule_id, severity, msg, None, None, None));
        }
    }

    diagnostics
}

fn check_doc_topic(ctx: &CharmContext, keyword: &str) -> bool {
    if ctx.readme_content.to_lowercase().contains(keyword) {
        return true;
    }
    let docs_dir = ctx.charm_dir.join("docs");
    if docs_dir.is_dir() {
        for entry in WalkDir::new(&docs_dir).follow_links(true) {
            if let Ok(e) = entry {
                if e.file_type().is_file()
                    && e.path().extension().map_or(false, |ext| ext == "md")
                {
                    if let Ok(content) = std::fs::read_to_string(e.path()) {
                        if content.to_lowercase().contains(keyword) {
                            return true;
                        }
                    }
                }
            }
        }
    }
    false
}

// ── LIB (Libraries) ─────────────────────────────────────────────────

fn check_libraries(ctx: &CharmContext) -> Vec<Diagnostic> {
    // Most charm libraries still require `charmcraft fetch-libs`.  A subset
    // has been lifted into the `canonical/charmlibs` monorepo and published
    // to PyPI under the `charmlibs-*` namespace; the import path also
    // changes (`charms.foo.vN.bar` → `charmlibs.bar`).  See
    // `design/UPSTREAM_AUDIT.md` for the audit log.  Values are
    // (PyPI package, import hint shown to the user).
    let pypi_map: &[(&str, &str, &str)] = &[
        (
            "certificate_transfer_interface",
            "charmlibs-interfaces-certificate-transfer",
            "from charmlibs.interfaces import certificate_transfer",
        ),
        (
            "tls_certificates_interface",
            "charmlibs-interfaces-tls-certificates",
            "from charmlibs.interfaces import tls_certificates",
        ),
    ];
    let pypi_lookup: std::collections::HashMap<&str, (&str, &str)> = pypi_map
        .iter()
        .map(|(k, pkg, hint)| (*k, (*pkg, *hint)))
        .collect();

    // operator_libs_linux splits by submodule; each piece is a separate
    // charmlibs-* PyPI package.
    let op_libs_submodules: &[(&str, &str, &str)] = &[
        ("apt", "charmlibs-apt", "from charmlibs import apt"),
        ("snap", "charmlibs-snap", "from charmlibs import snap"),
        ("passwd", "charmlibs-passwd", "from charmlibs import passwd"),
        ("sysctl", "charmlibs-sysctl", "from charmlibs import sysctl"),
        ("systemd", "charmlibs-systemd", "from charmlibs import systemd"),
    ];
    let op_libs_lookup: std::collections::HashMap<&str, (&str, &str)> = op_libs_submodules
        .iter()
        .map(|(k, pkg, hint)| (*k, (*pkg, *hint)))
        .collect();

    let import_re = Regex::new(r"from\s+charms\.(\w+)\.v\d+\.(\w+)").unwrap();

    let mut diagnostics = Vec::new();
    let mut seen = HashSet::new();

    for (path, content) in &ctx.python_sources {
        for cap in import_re.captures_iter(content) {
            let prefix = cap.get(1).unwrap().as_str();
            let submodule = cap.get(2).unwrap().as_str();
            let key = format!("{prefix}.{submodule}");
            if !seen.insert(key) {
                continue;
            }
            let line_no = content[..cap.get(0).unwrap().start()]
                .chars()
                .filter(|c| *c == '\n')
                .count()
                + 1;

            let resolved = if prefix == "operator_libs_linux" {
                op_libs_lookup.get(submodule).copied()
            } else {
                pypi_lookup.get(prefix).copied()
            };

            if let Some((pypi_name, import_hint)) = resolved {
                diagnostics.push(diag(
                    "LIB001",
                    Severity::Warning,
                    &format!(
                        "charms.{prefix}.v*.{submodule} — replace with PyPI package \
                         '{pypi_name}' ({import_hint})"
                    ),
                    Some(&path.to_string_lossy()),
                    Some(line_no),
                    Some(&format!("pip install {pypi_name}")),
                ));
            } else {
                diagnostics.push(diag(
                    "LIB002",
                    Severity::Info,
                    &format!(
                        "charms.{prefix}.v*.{submodule} — no PyPI equivalent yet; continue \
                         using `charmcraft fetch-libs`"
                    ),
                    Some(&path.to_string_lossy()),
                    Some(line_no),
                    None,
                ));
            }
        }
    }

    diagnostics
}

// ── CC (Charmcraft Compatibility) ────────────────────────────────────

fn check_charmcraft_compat(ctx: &CharmContext) -> Vec<Diagnostic> {
    let mut diagnostics = Vec::new();

    // CC001: deprecated series.
    if ctx.metadata.contains_key("series") {
        diagnostics.push(diag(
            "CC001",
            Severity::Warning,
            "'series' is deprecated in charm metadata — use 'bases' or 'platforms' instead",
            Some("charmcraft.yaml"),
            None,
            Some("Remove 'series' and use 'bases' or 'platforms'"),
        ));
    }

    // CC002: naming conventions (underscores).
    for opt_name in ctx.config_options.keys() {
        if opt_name.contains('_') {
            diagnostics.push(diag(
                "CC002",
                Severity::Warning,
                &format!(
                    "Config option '{opt_name}' uses underscores — prefer hyphens ('{}')",
                    opt_name.replace('_', "-")
                ),
                Some("charmcraft.yaml"),
                None,
                None,
            ));
        }
    }
    for (action_name, action_def) in &ctx.actions {
        if action_name.contains('_') {
            diagnostics.push(diag(
                "CC002",
                Severity::Warning,
                &format!(
                    "Action '{action_name}' uses underscores — prefer hyphens ('{}')",
                    action_name.replace('_', "-")
                ),
                Some("charmcraft.yaml"),
                None,
                None,
            ));
        }
        if let Some(m) = value_as_map(action_def) {
            let params = m
                .get(Value::String("params".into()))
                .or_else(|| m.get(Value::String("parameters".into())));
            if let Some(params_val) = params {
                if let Some(params_map) = value_as_map(params_val) {
                    let properties = params_map
                        .get(Value::String("properties".into()))
                        .and_then(|v| value_as_map(v))
                        .unwrap_or(params_map);
                    for pk in properties.keys() {
                        if let Value::String(param_name) = pk {
                            if param_name.contains('_') {
                                diagnostics.push(diag(
                                    "CC002",
                                    Severity::Warning,
                                    &format!(
                                        "Action '{action_name}' parameter '{param_name}' uses underscores — prefer hyphens ('{}')",
                                        param_name.replace('_', "-")
                                    ),
                                    Some("charmcraft.yaml"),
                                    None,
                                    None,
                                ));
                            }
                        }
                    }
                }
            }
        }
    }

    // CC003: entrypoint issues.
    let dispatch = ctx.charm_dir.join("dispatch");
    if dispatch.exists() {
        if let Ok(content) = std::fs::read_to_string(&dispatch) {
            let re = Regex::new(r"(?:exec\s+)?[./]*(\S+\.py)").unwrap();
            if let Some(cap) = re.captures(&content) {
                let entrypoint_rel = cap.get(1).unwrap().as_str();
                let entrypoint = ctx.charm_dir.join(entrypoint_rel);
                if !entrypoint.exists() {
                    diagnostics.push(diag(
                        "CC003",
                        Severity::Error,
                        &format!(
                            "Entrypoint '{entrypoint_rel}' referenced in dispatch does not exist"
                        ),
                        Some("dispatch"),
                        None,
                        None,
                    ));
                } else if !entrypoint.is_file() {
                    diagnostics.push(diag(
                        "CC003",
                        Severity::Error,
                        &format!("Entrypoint '{entrypoint_rel}' is not a regular file"),
                        Some("dispatch"),
                        None,
                        None,
                    ));
                } else {
                    #[cfg(unix)]
                    {
                        use std::os::unix::fs::PermissionsExt;
                        if let Ok(meta) = std::fs::metadata(&entrypoint) {
                            if meta.permissions().mode() & 0o111 == 0 {
                                diagnostics.push(diag(
                                    "CC003",
                                    Severity::Error,
                                    &format!("Entrypoint '{entrypoint_rel}' is not executable"),
                                    Some(entrypoint_rel),
                                    None,
                                    Some(&format!("Run: chmod +x {entrypoint_rel}")),
                                ));
                            }
                        }
                    }
                }
            }
        }
    }

    // CC004: no ops.main() call.
    let all_src = src_content(ctx);
    let has_ops = Regex::new(r"\bimport\s+ops\b|from\s+ops\b")
        .unwrap()
        .is_match(&all_src);
    if has_ops {
        let has_main = Regex::new(r"ops\.main\s*\(|main\s*\(\s*\w+Charm\s*\)")
            .unwrap()
            .is_match(&all_src);
        if !has_main {
            diagnostics.push(diag(
                "CC004",
                Severity::Warning,
                "Charm source imports ops but does not call ops.main()",
                None,
                None,
                Some("Add ops.main(MyCharm) at the end of the entrypoint"),
            ));
        }
    }

    // CC005: unknown top-level fields.
    let known_top_level: HashSet<&str> = [
        "name", "type", "title", "display-name", "summary", "description", "docs", "issues",
        "source", "website", "contact", "maintainers", "base", "build-base", "bases",
        "platforms", "parts", "extensions", "requires", "provides", "peers", "extra-bindings",
        "config", "actions", "containers", "resources", "storage", "devices", "charm-libs",
        "links", "subordinate", "assumes", "terms", "series", "min-juju-version", "analysis",
    ]
    .into_iter()
    .collect();

    for key in ctx.metadata.keys() {
        if !known_top_level.contains(key.as_str()) {
            let hint = suggest_closest(key, &known_top_level);
            diagnostics.push(diag(
                "CC005",
                Severity::Warning,
                &format!(
                    "Unrecognised top-level field '{key}' in charmcraft.yaml — possible typo"
                ),
                Some("charmcraft.yaml"),
                None,
                hint.as_deref(),
            ));
        }
    }

    // CC006: unknown resource fields.
    let known_resource_fields: HashSet<&str> =
        ["type", "description", "filename", "upstream-source"]
            .into_iter()
            .collect();

    if let Some(Value::Mapping(resources)) = ctx.metadata.get("resources") {
        for (res_key, res_val) in resources {
            if let (Value::String(res_name), Some(res_map)) = (res_key, value_as_map(res_val)) {
                for field_key in res_map.keys() {
                    if let Value::String(field) = field_key {
                        if !known_resource_fields.contains(field.as_str()) {
                            let hint = suggest_closest(field, &known_resource_fields);
                            diagnostics.push(diag(
                                "CC006",
                                Severity::Warning,
                                &format!(
                                    "Unrecognised field '{field}' in resource '{res_name}' — possible typo"
                                ),
                                Some("charmcraft.yaml"),
                                None,
                                hint.as_deref(),
                            ));
                        }
                    }
                }
            }
        }
    }

    diagnostics
}

// ── STS (Status Reporting) ───────────────────────────────────────────

fn check_status(ctx: &CharmContext) -> Vec<Diagnostic> {
    let checks: &[(&str, &str, &str)] = &[
        (
            r"(?i)missing.*config|config.*missing|no.*config",
            "STS001",
            "No BlockedStatus for missing required configuration",
        ),
        (
            r"(?i)conflict.*config|invalid.*config|config.*invalid",
            "STS002",
            "No BlockedStatus for conflicting/invalid configuration",
        ),
        (
            r"(?i)missing.*relation|relation.*missing|no.*relation",
            "STS003",
            "No status set for missing relations",
        ),
    ];

    let source = src_content(ctx);
    if source.is_empty() {
        return Vec::new();
    }

    let has_status = Regex::new(r"(?:Blocked|Waiting|Maintenance)Status")
        .unwrap()
        .is_match(&source);

    let mut diagnostics = Vec::new();
    for &(pattern, rule_id, msg) in checks {
        let re = Regex::new(pattern).unwrap();
        let has_condition = re.is_match(&source);
        if !(has_condition && has_status) {
            diagnostics.push(diag(rule_id, Severity::Warning, msg, None, None, None));
        }
    }

    diagnostics
}

// ── Levenshtein distance ─────────────────────────────────────────────

fn edit_distance(a: &str, b: &str, threshold: usize) -> usize {
    if a.len().abs_diff(b.len()) >= threshold {
        return threshold;
    }
    let b_chars: Vec<char> = b.chars().collect();
    let mut prev: Vec<usize> = (0..=b_chars.len()).collect();
    for (i, ca) in a.chars().enumerate() {
        let mut curr = vec![i + 1];
        for (j, &cb) in b_chars.iter().enumerate() {
            let cost = if ca == cb { 0 } else { 1 };
            curr.push(
                (prev[j + 1] + 1)
                    .min(curr[j] + 1)
                    .min(prev[j] + cost),
            );
        }
        prev = curr;
    }
    prev[b_chars.len()]
}

fn suggest_closest(typo: &str, known: &HashSet<&str>) -> Option<String> {
    let mut best: Option<&str> = None;
    let mut best_dist = 3usize;
    for &candidate in known {
        let d = edit_distance(typo, candidate, best_dist);
        if d < best_dist {
            best_dist = d;
            best = Some(candidate);
        }
    }
    best.map(|b| format!("Did you mean '{b}'?"))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::context;

    fn write(path: &std::path::Path, content: &str) {
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent).unwrap();
        }
        std::fs::write(path, content).unwrap();
    }

    /// Build a charm fixture directory with an arbitrary charmcraft.yaml body.
    fn charm_with_yaml(yaml: &str) -> tempfile::TempDir {
        let dir = tempfile::tempdir().unwrap();
        std::fs::create_dir(dir.path().join("src")).unwrap();
        write(&dir.path().join("charmcraft.yaml"), yaml);
        dir
    }

    /// Populate a full charm passing most rules.
    fn full_charm() -> tempfile::TempDir {
        let dir = charm_with_yaml(
            "name: test-charm\n\
             display-name: Test Charm\n\
             summary: A test charm\n\
             description: A test charm for unit tests.\n\
             docs: https://example.com/docs\n\
             issues: https://example.com/issues\n\
             source: https://example.com/source\n\
             requires:\n  \
               tracing:\n    interface: tracing\n  \
               logging:\n    interface: loki_push_api\n  \
               grafana-dashboard:\n    interface: grafana_dashboard\n  \
               certificates:\n    interface: tls-certificates\n\
             provides:\n  \
               metrics-endpoint:\n    interface: prometheus_scrape\n\
             config:\n  \
               options:\n    \
                 port:\n      type: int\n      default: 8080\n      description: HTTP port\n\
             actions:\n  \
               get-health:\n    description: Check health\n  \
               pause:\n    description: Pause\n  \
               resume:\n    description: Resume\n",
        );
        write(
            &dir.path().join("src/charm.py"),
            "import ops\n\
             from ops import BlockedStatus, WaitingStatus\n\
             \n\
             def main(charm: ops.CharmBase) -> None:\n    \
                 pass\n\
             \n\
             ops.main(TestCharm)\n\
             # missing config handling\n\
             # invalid config combination\n\
             # missing relation handling\n",
        );
        write(&dir.path().join("requirements.txt"), "ops\nops-tracing\n");
        write(
            &dir.path().join("README.md"),
            "# Test\n\n## Installation\n\n## Configuration\n\n## Usage\n\n## Troubleshooting\n",
        );
        write(&dir.path().join("LICENSE"), "Apache-2.0");
        write(&dir.path().join("icon.svg"), "<svg/>");
        write(&dir.path().join("tests/unit/test_charm.py"), "def test_x(): pass\n");
        write(&dir.path().join("tests/integration/test_charm.py"), "def test_x(): pass\n");
        dir
    }

    fn run_rules(dir: &std::path::Path) -> Vec<Diagnostic> {
        let ctx = context::build_context(dir);
        run_all(&ctx)
    }

    fn rule_ids(diagnostics: &[Diagnostic]) -> BTreeSet<String> {
        diagnostics.iter().map(|d| d.rule_id.clone()).collect()
    }

    // ── META rules ──────────────────────────────────────────────

    #[test]
    fn missing_name_is_error() {
        let dir = charm_with_yaml("display-name: X\n");
        let diags = run_rules(dir.path());
        let meta001: Vec<&Diagnostic> = diags.iter().filter(|d| d.rule_id == "META001").collect();
        assert_eq!(meta001.len(), 1);
        assert_eq!(meta001[0].severity, Severity::Error);
    }

    #[test]
    fn full_metadata_emits_no_meta_diagnostics() {
        let dir = full_charm();
        let diags = run_rules(dir.path());
        let metas: Vec<&Diagnostic> =
            diags.iter().filter(|d| d.rule_id.starts_with("META")).collect();
        assert!(metas.is_empty(), "got: {metas:?}");
    }

    // ── COS rules ───────────────────────────────────────────────

    #[test]
    fn missing_cos_relations_reported() {
        let dir = charm_with_yaml("name: test\n");
        let ids = rule_ids(&run_rules(dir.path()));
        for wanted in ["COS001", "COS002", "COS003", "COS004", "COS005"] {
            assert!(ids.contains(wanted), "missing {wanted}");
        }
    }

    #[test]
    fn full_charm_has_no_cos_diagnostics() {
        let dir = full_charm();
        let ids = rule_ids(&run_rules(dir.path()));
        assert!(
            !ids.iter().any(|id| id.starts_with("COS")),
            "got: {ids:?}",
        );
    }

    #[test]
    fn ops_tracing_in_requirements_suppresses_cos005() {
        let dir = charm_with_yaml("name: test\n");
        write(&dir.path().join("requirements.txt"), "ops\nops-tracing\n");
        let ids = rule_ids(&run_rules(dir.path()));
        assert!(!ids.contains("COS005"));
    }

    // ── TEST rules ──────────────────────────────────────────────

    #[test]
    fn missing_tests_emit_test001_and_test002() {
        let dir = charm_with_yaml("name: test\n");
        let ids = rule_ids(&run_rules(dir.path()));
        assert!(ids.contains("TEST001"));
        assert!(ids.contains("TEST002"));
    }

    #[test]
    fn harness_import_flagged_as_test003() {
        let dir = charm_with_yaml("name: test\n");
        write(
            &dir.path().join("tests/test_charm.py"),
            "from ops.testing import Harness\n",
        );
        let ids = rule_ids(&run_rules(dir.path()));
        assert!(ids.contains("TEST003"));
    }

    // ── DEP rules ───────────────────────────────────────────────

    #[test]
    fn stored_state_detected() {
        let dir = charm_with_yaml("name: test\n");
        write(
            &dir.path().join("src/charm.py"),
            "class MyCharm:\n    _stored = StoredState()\n",
        );
        let ids = rule_ids(&run_rules(dir.path()));
        assert!(ids.contains("DEP001"));
    }

    #[test]
    fn clean_source_emits_no_deprecated_rules() {
        let dir = charm_with_yaml("name: test\n");
        write(
            &dir.path().join("src/charm.py"),
            "import ops\n\nclass MyCharm(ops.CharmBase): pass\n",
        );
        let ids = rule_ids(&run_rules(dir.path()));
        assert!(!ids.iter().any(|id| id.starts_with("DEP")));
    }

    // ── LIB rules ───────────────────────────────────────────────

    #[test]
    fn known_pypi_lib_flagged_as_lib001() {
        // tls_certificates_interface has a real PyPI replacement.
        let dir = charm_with_yaml("name: test\n");
        write(
            &dir.path().join("src/charm.py"),
            "from charms.tls_certificates_interface.v3.tls_certificates \
             import TLSCertificatesRequiresV3\n",
        );
        let diagnostics = run_rules(dir.path());
        let ids = rule_ids(&diagnostics);
        assert!(ids.contains("LIB001"));
        // The message surfaces both the PyPI name and the new import path.
        let lib001 = diagnostics
            .iter()
            .find(|d| d.rule_id == "LIB001")
            .expect("LIB001 diagnostic");
        assert!(lib001.message.contains("charmlibs-interfaces-tls-certificates"));
        assert!(lib001
            .message
            .contains("from charmlibs.interfaces import tls_certificates"));
    }

    #[test]
    fn operator_libs_linux_submodule_flagged_as_lib001() {
        // operator_libs_linux splits per submodule — `apt` → `charmlibs-apt`.
        let dir = charm_with_yaml("name: test\n");
        write(
            &dir.path().join("src/charm.py"),
            "from charms.operator_libs_linux.v0.apt import DebianPackage\n",
        );
        let diagnostics = run_rules(dir.path());
        let ids = rule_ids(&diagnostics);
        assert!(ids.contains("LIB001"));
        let lib001 = diagnostics
            .iter()
            .find(|d| d.rule_id == "LIB001")
            .expect("LIB001 diagnostic");
        assert!(lib001.message.contains("charmlibs-apt"));
    }

    #[test]
    fn observability_libs_still_need_fetch_libs() {
        // grafana_k8s has no PyPI equivalent yet — LIB002, not LIB001.
        let dir = charm_with_yaml("name: test\n");
        write(
            &dir.path().join("src/charm.py"),
            "from charms.grafana_k8s.v0.grafana_dashboard import GrafanaDashboard\n",
        );
        let ids = rule_ids(&run_rules(dir.path()));
        assert!(ids.contains("LIB002"));
        assert!(!ids.contains("LIB001"));
    }

    #[test]
    fn unknown_charms_lib_flagged_as_lib002() {
        let dir = charm_with_yaml("name: test\n");
        write(
            &dir.path().join("src/charm.py"),
            "from charms.my_custom_lib.v1.module import Foo\n",
        );
        let ids = rule_ids(&run_rules(dir.path()));
        assert!(ids.contains("LIB002"));
    }

    // ── ACT rules ───────────────────────────────────────────────

    #[test]
    fn missing_expected_actions_reported() {
        let dir = charm_with_yaml("name: test\n");
        let ids = rule_ids(&run_rules(dir.path()));
        for wanted in ["ACT001", "ACT002", "ACT003"] {
            assert!(ids.contains(wanted), "missing {wanted}");
        }
    }

    #[test]
    fn action_aliases_accepted() {
        let dir = charm_with_yaml(
            "name: test\nactions:\n  \
             health-check:\n    description: Check\n  \
             stop:\n    description: Stop\n  \
             start:\n    description: Start\n",
        );
        let ids = rule_ids(&run_rules(dir.path()));
        assert!(!ids.contains("ACT001"));
        assert!(!ids.contains("ACT002"));
        assert!(!ids.contains("ACT003"));
    }

    #[test]
    fn action_without_description_flagged_as_act004() {
        let dir = charm_with_yaml("name: test\nactions:\n  backup: {}\n");
        let ids = rule_ids(&run_rules(dir.path()));
        assert!(ids.contains("ACT004"));
    }

    // ── CFG rules ───────────────────────────────────────────────

    #[test]
    fn config_option_missing_fields_reported() {
        let dir = charm_with_yaml(
            "name: test\nconfig:\n  options:\n    port: {}\n",
        );
        let ids = rule_ids(&run_rules(dir.path()));
        for wanted in ["CFG001", "CFG002", "CFG003"] {
            assert!(ids.contains(wanted), "missing {wanted}");
        }
    }

    // ── SEC rules ───────────────────────────────────────────────

    #[test]
    fn plain_password_config_triggers_sec001() {
        let dir = charm_with_yaml(
            "name: test\nconfig:\n  options:\n    admin-password:\n      type: string\n      description: Admin password\n",
        );
        write(&dir.path().join("src/charm.py"), "import ops\n");
        let ids = rule_ids(&run_rules(dir.path()));
        assert!(ids.contains("SEC001"));
    }

    #[test]
    fn juju_secrets_suppresses_sec001() {
        let dir = charm_with_yaml(
            "name: test\nconfig:\n  options:\n    admin-password:\n      type: string\n      description: Password\n",
        );
        write(
            &dir.path().join("src/charm.py"),
            "import ops\n# Uses juju secret API\nSecretChanged\n",
        );
        let ids = rule_ids(&run_rules(dir.path()));
        assert!(!ids.contains("SEC001"));
    }

    // ── STR rules ───────────────────────────────────────────────

    #[test]
    fn missing_structure_files_reported() {
        let dir = charm_with_yaml("name: test\n");
        let ids = rule_ids(&run_rules(dir.path()));
        for wanted in ["STR001", "STR002", "STR003"] {
            assert!(ids.contains(wanted), "missing {wanted}");
        }
    }

    #[test]
    fn full_charm_has_no_structure_diagnostics() {
        let dir = full_charm();
        let ids = rule_ids(&run_rules(dir.path()));
        assert!(!ids.iter().any(|id| id.starts_with("STR")));
    }

    // ── CC rules ────────────────────────────────────────────────

    #[test]
    fn series_field_triggers_cc001() {
        let dir = charm_with_yaml("name: test\nseries:\n  - jammy\n");
        let ids = rule_ids(&run_rules(dir.path()));
        assert!(ids.contains("CC001"));
    }

    #[test]
    fn underscore_config_option_triggers_cc002() {
        let dir = charm_with_yaml(
            "name: test\nconfig:\n  options:\n    http_port:\n      type: int\n      default: 80\n      description: Port\n",
        );
        let ids = rule_ids(&run_rules(dir.path()));
        assert!(ids.contains("CC002"));
    }

    #[test]
    fn unknown_top_level_field_triggers_cc005_with_hint() {
        let dir = charm_with_yaml("name: test\nsumarry: typo\n");
        let diags = run_rules(dir.path());
        let cc005: Vec<&Diagnostic> = diags.iter().filter(|d| d.rule_id == "CC005").collect();
        assert_eq!(cc005.len(), 1);
        let hint = cc005[0].fix_hint.as_deref().unwrap_or("");
        assert!(hint.contains("summary"), "got hint: {hint}");
    }

    // ── Helper-level assertions ─────────────────────────────────

    #[test]
    fn edit_distance_short_circuits_on_length_gap() {
        assert_eq!(edit_distance("abc", "abcdefghij", 3), 3);
    }

    #[test]
    fn edit_distance_reports_exact_small_distance() {
        assert_eq!(edit_distance("summary", "sumarry", 3), 2);
        assert_eq!(edit_distance("summary", "summary", 3), 0);
    }

    #[test]
    fn suggest_closest_returns_near_match() {
        let set: HashSet<&str> = ["summary", "description", "name"].into_iter().collect();
        assert_eq!(
            suggest_closest("sumary", &set).as_deref(),
            Some("Did you mean 'summary'?"),
        );
    }

    #[test]
    fn suggest_closest_returns_none_for_far_match() {
        let set: HashSet<&str> = ["summary"].into_iter().collect();
        assert!(suggest_closest("completely-different", &set).is_none());
    }
}
