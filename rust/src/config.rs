//! Configuration loader for charmlint.

use crate::models::Severity;
use std::collections::BTreeMap;
use std::path::Path;

/// Resolved lint configuration.
#[derive(Debug, Default)]
pub struct LintConfig {
    pub severity_overrides: BTreeMap<String, String>,
    pub select: Vec<String>,
    pub ignore: Vec<String>,
    pub min_severity: Option<Severity>,
}

impl LintConfig {
    pub fn from_yaml(data: &serde_yaml::Value) -> Self {
        let mut config = Self::default();

        if let Some(mapping) = data.as_mapping() {
            // Parse rules section.
            if let Some(serde_yaml::Value::Mapping(rules)) =
                mapping.get(serde_yaml::Value::String("rules".into()))
            {
                for (k, v) in rules {
                    if let (Some(key), Some(val)) = (k.as_str(), v.as_str()) {
                        config
                            .severity_overrides
                            .insert(key.to_string(), val.to_lowercase());
                    }
                }
            }

            // Parse select.
            if let Some(serde_yaml::Value::Sequence(seq)) =
                mapping.get(serde_yaml::Value::String("select".into()))
            {
                for item in seq {
                    if let Some(s) = item.as_str() {
                        config.select.push(s.to_string());
                    }
                }
            }

            // Parse ignore.
            if let Some(serde_yaml::Value::Sequence(seq)) =
                mapping.get(serde_yaml::Value::String("ignore".into()))
            {
                for item in seq {
                    if let Some(s) = item.as_str() {
                        config.ignore.push(s.to_string());
                    }
                }
            }

            // Parse severity.
            if let Some(serde_yaml::Value::String(sev)) =
                mapping.get(serde_yaml::Value::String("severity".into()))
            {
                config.min_severity = Severity::from_str_loose(sev);
            }
        }

        config
    }
}

/// Load configuration from a `.charmlint.yaml` file.
pub fn load_config(charm_dir: &Path, config_path: Option<&Path>) -> LintConfig {
    let path = match config_path {
        Some(p) => p.to_path_buf(),
        None => charm_dir.join(".charmlint.yaml"),
    };

    if !path.exists() {
        return LintConfig::default();
    }

    let content = match std::fs::read_to_string(&path) {
        Ok(c) => c,
        Err(_) => return LintConfig::default(),
    };

    let data: serde_yaml::Value = match serde_yaml::from_str(&content) {
        Ok(d) => d,
        Err(_) => return LintConfig::default(),
    };

    LintConfig::from_yaml(&data)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn yaml(s: &str) -> serde_yaml::Value {
        serde_yaml::from_str(s).unwrap()
    }

    #[test]
    fn empty_mapping_yields_default_config() {
        let config = LintConfig::from_yaml(&yaml("{}"));
        assert!(config.severity_overrides.is_empty());
        assert!(config.select.is_empty());
        assert!(config.ignore.is_empty());
        assert!(config.min_severity.is_none());
    }

    #[test]
    fn rules_section_parsed_into_severity_overrides() {
        let config = LintConfig::from_yaml(&yaml(
            "rules:\n  COS005: error\n  STR002: off\n",
        ));
        assert_eq!(config.severity_overrides.get("COS005").unwrap(), "error");
        assert_eq!(config.severity_overrides.get("STR002").unwrap(), "off");
    }

    #[test]
    fn rule_severity_lowercased() {
        let config = LintConfig::from_yaml(&yaml("rules:\n  COS001: ERROR\n"));
        assert_eq!(config.severity_overrides.get("COS001").unwrap(), "error");
    }

    #[test]
    fn select_and_ignore_parsed_as_lists() {
        let config = LintConfig::from_yaml(&yaml(
            "select:\n  - COS\n  - META\nignore:\n  - STR003\n",
        ));
        assert_eq!(config.select, vec!["COS".to_string(), "META".to_string()]);
        assert_eq!(config.ignore, vec!["STR003".to_string()]);
    }

    #[test]
    fn severity_field_sets_min_severity() {
        let config = LintConfig::from_yaml(&yaml("severity: warning\n"));
        assert_eq!(config.min_severity, Some(Severity::Warning));
    }

    #[test]
    fn unknown_severity_becomes_none() {
        let config = LintConfig::from_yaml(&yaml("severity: bogus\n"));
        assert!(config.min_severity.is_none());
    }

    #[test]
    fn load_config_returns_default_when_no_file() {
        let tmp = tempfile::tempdir().unwrap();
        let config = load_config(tmp.path(), None);
        assert!(config.severity_overrides.is_empty());
    }

    #[test]
    fn load_config_reads_charmlint_yaml_from_charm_dir() {
        let tmp = tempfile::tempdir().unwrap();
        std::fs::write(
            tmp.path().join(".charmlint.yaml"),
            "rules:\n  COS005: error\nignore:\n  - STR002\n",
        )
        .unwrap();
        let config = load_config(tmp.path(), None);
        assert_eq!(config.severity_overrides.get("COS005").unwrap(), "error");
        assert!(config.ignore.contains(&"STR002".to_string()));
    }

    #[test]
    fn load_config_honours_explicit_path() {
        let tmp = tempfile::tempdir().unwrap();
        let custom = tmp.path().join("custom.yaml");
        std::fs::write(&custom, "select:\n  - COS\n").unwrap();
        let config = load_config(tmp.path(), Some(&custom));
        assert_eq!(config.select, vec!["COS".to_string()]);
    }

    #[test]
    fn load_config_returns_default_on_malformed_yaml() {
        let tmp = tempfile::tempdir().unwrap();
        std::fs::write(tmp.path().join(".charmlint.yaml"), "not: [valid: yaml:\n").unwrap();
        let config = load_config(tmp.path(), None);
        assert!(config.select.is_empty());
    }
}
