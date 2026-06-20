//! Fuzz target: arbitrary bytes → YAML → `LintConfig::from_yaml`.
//!
//! `LintConfig::from_yaml` is a defensive walk over a `serde_yaml::Value`
//! that emits a default config for anything it doesn't recognise.  The
//! fuzz target asserts the documented contract: any byte sequence that
//! `serde_yaml` happens to parse into a `Value` must feed cleanly through
//! `from_yaml` without panicking, regardless of how malformed or
//! pathological the resulting structure is.
#![no_main]

use charmlint_rs::config::LintConfig;
use libfuzzer_sys::fuzz_target;

fuzz_target!(|data: &[u8]| {
    if let Ok(value) = serde_yaml::from_slice::<serde_yaml::Value>(data) {
        let _ = LintConfig::from_yaml(&value);
    }
});
