//! Fuzz target: arbitrary UTF-8 → `Severity::from_str_loose`.
//!
//! `Severity::from_str_loose` is called on raw user input from the
//! `--severity` CLI flag and the `severity:` key of `.charmlint.yaml`.
//! The fuzz target asserts the parser is *total* on any UTF-8 input —
//! every byte sequence either maps to a known severity or returns
//! `None`, never panics, and never loops.
#![no_main]

use charmlint_rs::models::Severity;
use libfuzzer_sys::fuzz_target;

fuzz_target!(|data: &[u8]| {
    if let Ok(s) = std::str::from_utf8(data) {
        let _ = Severity::from_str_loose(s);
    }
});
