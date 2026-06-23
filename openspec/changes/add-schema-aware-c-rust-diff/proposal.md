## Why

当前 CI 已能真实生成 C oracle report，但该 report 不是 fixture-driven，也没有和 Rust replay report 做 C/Rust 行为差分。下一步必须让 C 与 Rust 使用同一 fixture，并让 diff 能按 step/field 比较、跳过明确登记的 accepted differences。

English summary: C oracle generation is now real, but not yet comparable with Rust replay. This change adds the schema-aware C/Rust differential loop.

## What Changes

- Add a C/Rust comparable fixture that avoids known non-equivalent byte-layout fields.
- Make C oracle generation consume the fixture and emit replay-compatible step results.
- Update Rust `diff` to compare step ids, operation names, stable codes, values, counts, and entries instead of requiring whole-file byte equality.
- Apply accepted differences such as `image_hash`, report paths, backend/toolchain metadata, and human error messages.
- Update CI to compare Rust replay output with the generated C oracle report.

## Capabilities

### New Capabilities

- `schema-aware-c-rust-diff`: Covers fixture-driven C oracle replay, schema-aware Rust/C report comparison, accepted-difference handling, and CI failure on real behavior mismatch.

### Modified Capabilities

- None.

## Impact

- Updates `flashDB_rust/src/replay.rs` diff behavior.
- Adds or updates Rust differential tests and fixtures.
- Updates `flashDB_rust/oracle/` C oracle generation behavior.
- Updates `flashDB_rust/scripts/verify-ci.sh` to run Rust-vs-C diff after C oracle generation.
- Does not claim byte-for-byte FlashDB image equivalence; it proves behavior-level equivalence for the comparable fixture.
