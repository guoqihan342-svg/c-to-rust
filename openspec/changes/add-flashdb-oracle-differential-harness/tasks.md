## 1. Fixture and Report Contract

- [x] 1.1 Add deterministic fixture files for KVDB, TSDB, persistence/reopen, and abnormal paths.
- [x] 1.2 Add Rust replay report schema fields for fixture path, fixture hash, step results, values, entries, image hashes, and stable error codes.
- [x] 1.3 Add accepted-difference records for known Rust seed-layout gaps without hiding behavioral mismatches.

## 2. Rust Replay and Differential CLI

- [x] 2.1 Add stable `Error::code()` values for all first-party error variants.
- [x] 2.2 Implement `flashdb-rust replay --fixture <path> --report <path> [--backend memory|file]`.
- [x] 2.3 Implement `flashdb-rust diff --rust-report <path> --oracle-report <path> --report <path>`.
- [x] 2.4 Preserve existing `smoke`, `stress`, `inspect-image`, and `unsafe-scan` command behavior.

## 3. Tests and Evidence

- [x] 3.1 Add Rust tests for replay pass, stable error-code output, diff pass, and first-mismatch diff failure.
- [x] 3.2 Add evidence files for local Rust replay and comparison runs.
- [x] 3.3 Ensure evidence labels local C producer skip as `SKIPPED_LOCAL_NO_C_TOOLCHAIN` when no C compiler exists.

## 4. C Oracle Producer Contract

- [x] 4.1 Add `flashDB_rust/oracle/` contract docs and helper files for fixed FlashDB commit oracle generation.
- [x] 4.2 Add toolchain detection behavior or script docs that never claim C oracle success when C tools are missing.
- [x] 4.3 Document Linux/CI commands for generating C oracle reports compatible with the Rust diff command.

## 5. CI and Verification Scripts

- [x] 5.1 Update local verification script to include replay/diff smoke checks.
- [x] 5.2 Add or update CI workflow for Rust fmt/check/test, replay/diff, unsafe scan, OpenSpec validation, and release 10000-loop stress.
- [x] 5.3 Keep C oracle generation conditional in CI and record skip/failure evidence explicitly.

## 6. Validation

- [x] 6.1 Run `cargo fmt -- --check` in `flashDB_rust`.
- [x] 6.2 Run `cargo check` in `flashDB_rust`.
- [x] 6.3 Run `cargo test` in `flashDB_rust`.
- [x] 6.4 Run replay and diff smoke commands and write reports.
- [x] 6.5 Run CLI smoke, stress sample, and unsafe scan.
- [x] 6.6 Run release 10000-loop stress or preserve the latest recorded evidence if unchanged.
- [x] 6.7 Run `openspec validate "add-flashdb-oracle-differential-harness" --strict`.
- [x] 6.8 Run `openspec validate --all`.
- [x] 6.9 Run `git diff --check`.
