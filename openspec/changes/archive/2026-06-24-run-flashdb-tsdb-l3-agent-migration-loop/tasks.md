## 1. Slice Freeze And Context

- [x] 1.1 Freeze the `tsdb-append-query-status` L3 slice with Rust API list, C oracle operation list, fixture path, FlashDB source commit, backend matrix, accepted-difference policy, and timestamp monotonicity rule.
- [x] 1.2 Produce `validation/evidence/flashdb/l3-tsdb-append-query-status-context-pack.json` with TSDB Rust modules, replay operations, C oracle functions, related tests, fixture path, unsafe status, cache key, and rollback id.
- [x] 1.3 Produce `validation/evidence/flashdb/l3-tsdb-append-query-status-slice-contract.json` describing included behavior, excluded behavior, public API impact set, forbidden behavior-field differences, and pass/fail gates.
- [x] 1.4 Record bounded agent roles for TSDB slice review, C oracle review, evidence audit, patch review, and single-writer code application.

## 2. Fixture And Rust Tests

- [x] 2.1 Add `flashDB_rust/fixtures/l3-tsdb-append-query-status.json` with at least three strictly increasing timestamp appends, forward query, reversed query, status update, count-by-status, reopen, query-after-reopen, and metadata-only accepted differences.
- [x] 2.2 Add a Rust integration test that replays the L3 TSDB fixture through the file backend and asserts L3 metadata, slice id, core operations, status update, count, reopen, and query-after-reopen fields are present.
- [x] 2.3 Add a negative diff regression test that mutates TSDB value, status, count, entry id, timestamp, or query ordering and requires schema-aware diff failure.
- [x] 2.4 Extend persistence or TSDB targeted tests only if needed to cover status persistence after file reopen without broadening the slice.

## 3. Rust Replay And Behavior Parity

- [x] 3.1 Verify existing replay support for `ts.append`, `ts.query`, `ts.set_status`, `ts.count_status`, `ts.reopen`, and `ts.image_hash` covers the L3 fixture without parser changes.
- [x] 3.2 Implement the smallest Rust changes required for TSDB C/Rust parity, if any, without changing public API outside the TSDB impact set.
- [x] 3.3 Generate the Rust replay report at `validation/evidence/flashdb/l3-tsdb-append-query-status-rust-report.json`.
- [x] 3.4 Verify that TSDB behavior fields are never listed in accepted differences.

## 4. C Oracle And Schema Diff

- [x] 4.1 Generate local Windows C oracle toolchain evidence at `validation/evidence/flashdb/l3-tsdb-append-query-status-local-toolchain-evidence.json`.
- [x] 4.2 Generate the C oracle report at `validation/evidence/flashdb/l3-tsdb-append-query-status-c-oracle.json` on Linux/WSL/CI with `toolchain_status == C_ORACLE_GENERATED`.
- [x] 4.3 Generate C oracle producer evidence at `validation/evidence/flashdb/l3-tsdb-append-query-status-c-oracle-producer-evidence.json`.
- [x] 4.4 Run schema-aware diff and write `validation/evidence/flashdb/l3-tsdb-append-query-status-diff.json`.
- [x] 4.5 Record a negative diff artifact at `validation/evidence/flashdb/l3-tsdb-append-query-status-negative-diff.json` or in the test output proving TSDB behavior mutations fail.

## 5. Compile Self-Healing And Patch Evidence

- [x] 5.1 Run `cargo check --message-format=json` in `flashDB_rust` and write raw output to `validation/evidence/flashdb/l3-tsdb-append-query-status-rust-check.raw.jsonl`.
- [x] 5.2 Summarize rustc JSON into `validation/evidence/flashdb/l3-tsdb-append-query-status-rust-check.json` with status, error count, warnings, root cause keys, affected items, and rerun command.
- [x] 5.3 Parse any compiler errors into `validation/evidence/flashdb/error-events.jsonl` with code, primary span, related spans, rendered message, classifier, and affected TSDB/replay item.
- [x] 5.4 Record every automatic repair attempt in `validation/evidence/flashdb/patches.jsonl` with patch id, files, spans, reason, expected error delta, risk, rollback id, forbidden changes, AI usage, and verification commands.
- [x] 5.5 Enforce rollback/blocking when a repair repeats a root cause, introduces a new error category, widens unsafe, changes oracle contract, changes fixture behavior, or broadens accepted differences.

## 6. Unsafe, Cache, And Performance Evidence

- [x] 6.1 Run unsafe scan and write `validation/evidence/flashdb/l3-tsdb-append-query-status-unsafe-scan.json` with unsafe count, unsafe ratio, scanned files, ignored paths, and status.
- [x] 6.2 Write `validation/evidence/flashdb/l3-tsdb-append-query-status-unsafe-ledger.json`; keep first-party non-test unsafe at 0% for this slice.
- [x] 6.3 Add cache metadata for ContextPack and self-healing outputs keyed by source commit, TSDB/replay/oracle fixture hashes, Cargo.lock, command args, rustc version, feature/env, and context schema.
- [x] 6.4 Run TSDB performance smoke and write `validation/evidence/flashdb/l3-tsdb-append-query-status-performance-smoke.json` with backend, operation counters, elapsed time, command, and toolchain status.
- [x] 6.5 Do not introduce async runtime, internal multithreading, or concurrency changes to FlashDB Rust logic unless a design update and performance evidence justify it.

## 7. Final Verification And Summary

- [x] 7.1 Run `cargo fmt -- --check` in `flashDB_rust`.
- [x] 7.2 Run targeted TSDB and differential replay tests in `flashDB_rust`.
- [x] 7.3 Run `cargo check` and `cargo test` in `flashDB_rust`.
- [x] 7.4 Run CLI replay, schema diff, unsafe scan, and performance smoke for the selected TSDB fixture.
- [x] 7.5 Write `validation/evidence/flashdb/l3-tsdb-append-query-status-summary.json` and `.md` documenting scope, evidence paths, source commit, fixture hash, C oracle status, diff result, unsafe ratio, accepted differences, failures, and next slice recommendation.
- [x] 7.6 Run `openspec validate run-flashdb-tsdb-l3-agent-migration-loop --strict`, `openspec validate --all`, and `git diff --check`.
