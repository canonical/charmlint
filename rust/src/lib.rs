//! charmlint library entry point.
//!
//! The binary at `src/main.rs` remains the user-facing CLI; this `lib.rs`
//! exists only so the public modules can be reached from external test
//! and fuzz crates (notably `fuzz/`).  Each module also keeps its
//! `mod` declaration in `main.rs`, so the binary continues to build
//! independently of the library.
pub mod config;
pub mod context;
pub mod linter;
pub mod models;
pub mod rules;
