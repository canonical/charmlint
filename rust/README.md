# charmlint — Rust implementation

A charm-aware linter for Juju charms, implemented in Rust 2021.

## Extraction note

Extracted from [`tonyandrewmeyer/cantrip`](https://github.com/tonyandrewmeyer/cantrip)
at path `src/charmlint-rs/`,
commit `d2b15056b1e17a99c3e37130fd10d21ad1ab059d`. Git history was not preserved;
this is a fresh repository.

## Build

```bash
cargo build --release
./target/release/charmlint /path/to/charm
```

## Usage

```
charmlint [OPTIONS] [PATH]

Arguments:
  [PATH]  Path to the charm directory (default: .)

Options:
  --format <FORMAT>    Output format: text (default) or json
  --select <SELECT>    Comma-separated rule categories to enable (e.g. COS,META)
  --ignore <IGNORE>    Comma-separated rule IDs or categories to skip
  --severity <SEV>     Minimum severity: error | warning | info
  --config <PATH>      Path to .charmlint.yaml config file
  --strict             Exit 2 if warnings found (default: only errors exit 1)
  --no-colour          Disable ANSI colour output
```

## Running tests

```bash
cargo test
```

## Fuzz targets

```bash
cd fuzz
cargo +nightly fuzz run fuzz_lint_config_yaml
cargo +nightly fuzz run fuzz_severity_from_str
```

## Note on implementation drift

The Rust implementation covers a subset of the rules in the Python implementation.
Both share the same diagnostic model and configuration format, but the rule
catalogues have diverged during development — the Python implementation is the
primary reference. See the Python `README.md` for the full rule catalogue.
