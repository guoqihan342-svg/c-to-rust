## 1. Slice Freeze And Context

- [x] 1.1 Freeze the `kvdb-compact-overwrite` L3 slice with Rust API list, C oracle operation list, fixture path, FlashDB source commit, backend matrix, accepted-difference policy, and visible-compact boundary.
- [x] 1.2 Produce `validation/evidence/flashdb/l3-kvdb-compact-overwrite-context-pack.json` with KVDB Rust modules, replay operations, C oracle functions, related tests, fixture path, unsafe status, cache key, and rollback id.
- [x] 1.3 Produce `validation/evidence/flashdb/l3-kvdb-compact-overwrite-slice-contract.json` describing included behavior, excluded GC/sector-layout behavior, public API impact set, forbidden behavior-field differences, and pass/fail gates.
- [x] 1.4 Record bounded agent roles for KVDB slice review, C oracle compact-boundary review, evidence audit, patch review, and single-writer code application.

## 2. Fixture And Rust Tests

- [x] 2.1 Add `flashDB_rust/fixtures/l3-kvdb-compact-overwrite.json` with initial set, same-key overwrite, latest-value get, entries after overwrite, compact, reopen, latest-value get after reopen, delete, and missing get.
- [x] 2.2 Add a Rust integration test that replays the L3 KVDB compact/overwrite fixture through the file backend and asserts L3 metadata, slice id, overwrite value, entries, compact, reopen, and delete/missing-get fields are present.
- [x] 2.3 Add a negative diff regression test that mutates post-overwrite value or entries and requires schema-aware diff failure.
- [x] 2.4 Extend targeted KVDB tests only if needed to cover visible compact/reopen behavior without broadening the slice into native GC or sector layout.

## 3. Rust Replay And Behavior Parity

- [x] 3.1 Verify existing replay support for `kv.set`, `kv.get`, `kv.entries`, `kv.compact`, `kv.reopen`, and `kv.delete` covers the L3 fixture without parser changes.
- [x] 3.2 Implement the smallest Rust changes required for KVDB C/Rust visible-behavior parity, if any, without changing public API outside the KVDB impact set.
- [x] 3.3 Generate the Rust replay report at `validation/evidence/flashdb/l3-kvdb-compact-overwrite-rust-report.json`.
- [x] 3.4 Verify that KVDB behavior fields are never listed in accepted differences.

## 4. C Oracle And Schema Diff

- [x] 4.1 Generate local Windows C oracle toolchain evidence at `validation/evidence/flashdb/l3-kvdb-compact-overwrite-local-toolchain-evidence.json`.
- [x] 4.2 Generate the C oracle report at `validation/evidence/flashdb/l3-kvdb-compact-overwrite-c-oracle.json` on Linux/WSL/CI with `toolchain_status == C_ORACLE_GENERATED`.
- [x] 4.3 Generate C oracle producer evidence at `validation/evidence/flashdb/l3-kvdb-compact-overwrite-c-oracle-producer-evidence.json`.
- [x] 4.4 Run schema-aware diff and write `validation/evidence/flashdb/l3-kvdb-compact-overwrite-diff.json`.
- [x] 4.5 Record a negative diff artifact at `validation/evidence/flashdb/l3-kvdb-compact-overwrite-negative-diff.json` proving KVDB value or entries behavior mutations fail.

## 5. Compile Self-Healing And Patch Evidence

- [x] 5.1 Run `cargo check --message-format=json` in `flashDB_rust` and write raw output to `validation/evidence/flashdb/l3-kvdb-compact-overwrite-rust-check.raw.jsonl`.
- [x] 5.2 Summarize rustc JSON into `validation/evidence/flashdb/l3-kvdb-compact-overwrite-rust-check.json` with status, error count, warnings, root cause keys, affected items, and rerun command.
- [x] 5.3 Parse any compiler errors into `validation/evidence/flashdb/error-events.jsonl` with code, primary span, related spans, rendered message, classifier, and affected KVDB/replay item.
- [x] 5.4 Record every automatic repair attempt in `validation/evidence/flashdb/patches.jsonl` with patch id, files, spans, reason, expected error delta, risk, rollback id, forbidden changes, AI usage, and verification commands.
- [x] 5.5 Enforce rollback/blocking when a repair repeats a root cause, introduces a new error category, widens unsafe, changes oracle contract, changes fixture behavior, or broadens accepted differences.

## 6. Unsafe, Cache, And Performance Evidence

- [x] 6.1 Run unsafe scan and write `validation/evidence/flashdb/l3-kvdb-compact-overwrite-unsafe-scan.json` with unsafe count, unsafe ratio, scanned files, ignored paths, and status.
- [x] 6.2 Write `validation/evidence/flashdb/l3-kvdb-compact-overwrite-unsafe-ledger.json`; keep first-party non-test unsafe at 0% for this slice.
- [x] 6.3 Add cache metadata for ContextPack and self-healing outputs keyed by source commit, KVDB/replay/oracle fixture hashes, Cargo.lock, command args, rustc version, feature/env, and context schema.
- [x] 6.4 Run KVDB compact/overwrite performance smoke and write `validation/evidence/flashdb/l3-kvdb-compact-overwrite-performance-smoke.json` with backend, operation counters, elapsed time, command, and toolchain status.
- [x] 6.5 Do not introduce async runtime, internal multithreading, or concurrency changes to FlashDB Rust logic unless a design update and performance evidence justify it.

## 7. Final Verification And Summary

- [x] 7.1 Run `cargo fmt -- --check` in `flashDB_rust`.
- [x] 7.2 Run targeted KVDB and differential replay tests in `flashDB_rust`.
- [x] 7.3 Run `cargo check` and `cargo test` in `flashDB_rust`.
- [x] 7.4 Run CLI replay, schema diff, unsafe scan, and performance smoke for the selected KVDB fixture.
- [x] 7.5 Write `validation/evidence/flashdb/l3-kvdb-compact-overwrite-summary.json` and `.md` documenting visible-behavior scope, evidence paths, source commit, fixture hash, C oracle status, diff result, unsafe ratio, accepted differences, compact boundary, failures, and next slice recommendation.
- [x] 7.6 Run `openspec validate run-flashdb-kvdb-compact-overwrite-l3-loop --strict`, `openspec validate --all`, and `git diff --check`.
