## 1. Slice Freeze And Context

- [x] 1.1 Freeze the `kvdb-delete-missing-key` L3 slice with Rust API list, C oracle operation list, fixture path, FlashDB source commit, backend matrix, accepted-difference policy, and missing-delete boundary.
- [x] 1.2 Produce `validation/evidence/flashdb/l3-kvdb-delete-missing-key-context-pack.json` with KVDB Rust modules, replay operations, C oracle functions, related tests, fixture path, unsafe status, cache key, and rollback id.
- [x] 1.3 Produce `validation/evidence/flashdb/l3-kvdb-delete-missing-key-slice-contract.json` describing included behavior, excluded invalid-key/GC/sector-layout behavior, public API impact set, forbidden behavior-field differences, and pass/fail gates.
- [x] 1.4 Produce `validation/evidence/flashdb/l3-kvdb-delete-missing-key-impact-set.json` with allowed source, fixture, test, and evidence edits.
- [x] 1.5 Record bounded agent roles for C semantic review, Rust impact review, evidence naming review, patch review, and single-writer code application.

## 2. Fixture And Rust Tests

- [x] 2.1 Add `flashDB_rust/fixtures/l3-kvdb-delete-missing-key.json` with never-existing delete, missing get, entries, live-key set/get, existing delete setup, delete-after-delete, reopen, and post-reopen reads.
- [x] 2.2 Add a Rust integration test that replays the L3 KVDB delete-missing-key fixture through the file backend and asserts L3 metadata, slice id, missing-delete `FDB_KV_NAME_ERR`, recovery state, delete-after-delete, and reopen behavior.
- [x] 2.3 Add a negative diff regression test that mutates missing-delete status or code and requires schema-aware diff failure.
- [x] 2.4 Run the targeted Rust test before production code changes and persist the red failure at `validation/evidence/flashdb/l3-kvdb-delete-missing-key-red-test.log`.

## 3. Rust Replay And Behavior Parity

- [x] 3.1 Verify existing replay support for `kv.delete`, `kv.set`, `kv.get`, `kv.entries`, and `kv.reopen` covers the L3 fixture without parser changes.
- [x] 3.2 Implement the smallest Rust changes required for KVDB C/Rust visible-behavior parity, limited to missing-delete error mapping and `KvDb::delete` existence check.
- [x] 3.3 Update any Rust tests that depended on missing delete as success without broadening production behavior.
- [x] 3.4 Generate the Rust replay report at `validation/evidence/flashdb/l3-kvdb-delete-missing-key-rust-report.json`.
- [x] 3.5 Verify that KVDB behavior fields are never listed in accepted differences.

## 4. C Oracle And Schema Diff

- [x] 4.1 Generate local Windows C oracle toolchain evidence at `validation/evidence/flashdb/l3-kvdb-delete-missing-key-local-toolchain-evidence.json`.
- [x] 4.2 Generate the C oracle report at `validation/evidence/flashdb/l3-kvdb-delete-missing-key-c-oracle.json` on Linux/WSL/CI with `toolchain_status == C_ORACLE_GENERATED`.
- [x] 4.3 Generate C oracle producer evidence at `validation/evidence/flashdb/l3-kvdb-delete-missing-key-c-oracle-producer-evidence.json`.
- [x] 4.4 Run schema-aware diff and write `validation/evidence/flashdb/l3-kvdb-delete-missing-key-diff.json`.
- [x] 4.5 Record a mutated oracle report at `validation/evidence/flashdb/l3-kvdb-delete-missing-key-mutated-missing-delete-oracle.json`.
- [x] 4.6 Record a negative diff artifact at `validation/evidence/flashdb/l3-kvdb-delete-missing-key-negative-diff.json` proving missing-delete status or code mutations fail.

## 5. Compile Self-Healing And Patch Evidence

- [x] 5.1 Run `cargo check --message-format=json` in `flashDB_rust` and write raw output to `validation/evidence/flashdb/l3-kvdb-delete-missing-key-rust-check.raw.jsonl`.
- [x] 5.2 Summarize rustc JSON into `validation/evidence/flashdb/l3-kvdb-delete-missing-key-rust-check.json` with status, error count, warnings, root cause keys, affected items, and rerun command.
- [x] 5.3 Parse any compiler errors into `validation/evidence/flashdb/error-events.jsonl` with code, primary span, related spans, rendered message, classifier, and affected KVDB/replay item.
- [x] 5.4 Record every automatic repair attempt in `validation/evidence/flashdb/patches.jsonl` with patch id, files, spans, reason, expected error delta, risk, rollback id, forbidden changes, AI usage, and verification commands.
- [x] 5.5 Enforce rollback/blocking when a repair repeats a root cause, introduces a new error category, widens unsafe, changes oracle contract, changes fixture behavior, or broadens accepted differences.

## 6. Unsafe, Cache, And Performance Evidence

- [x] 6.1 Run unsafe scan and write `validation/evidence/flashdb/l3-kvdb-delete-missing-key-unsafe-scan.json` with unsafe count, unsafe ratio, scanned files, ignored paths, and status.
- [x] 6.2 Write `validation/evidence/flashdb/l3-kvdb-delete-missing-key-unsafe-ledger.json`; keep first-party non-test unsafe at 0% for this slice.
- [x] 6.3 Add cache metadata for ContextPack and self-healing outputs keyed by source commit, KVDB/replay/oracle fixture hashes, Cargo.lock, command args, rustc version, feature/env, and context schema.
- [x] 6.4 Run KVDB delete-missing-key performance smoke and write `validation/evidence/flashdb/l3-kvdb-delete-missing-key-performance-smoke.json` with backend, operation counters, elapsed time, command, and toolchain status.
- [x] 6.5 Do not introduce async runtime, internal multithreading, or concurrency changes to FlashDB Rust logic unless a design update and performance evidence justify it.

## 7. Final Verification And Summary

- [x] 7.1 Run `cargo fmt -- --check` in `flashDB_rust`.
- [x] 7.2 Run targeted KVDB and differential replay tests in `flashDB_rust`.
- [x] 7.3 Run `cargo check` and `cargo test` in `flashDB_rust`.
- [x] 7.4 Run CLI replay, schema diff, unsafe scan, and performance smoke for the selected KVDB fixture.
- [x] 7.5 Write `validation/evidence/flashdb/l3-kvdb-delete-missing-key-final-verification.json`.
- [x] 7.6 Write `validation/evidence/flashdb/l3-kvdb-delete-missing-key-summary.json` and `.md` documenting visible-behavior scope, evidence paths, source commit, fixture hash, C oracle status, diff result, unsafe ratio, accepted differences, missing-delete boundary, failures, and next slice recommendation.
- [x] 7.7 Run `openspec validate run-flashdb-kvdb-delete-missing-key-l3-loop --strict`, `openspec validate --all`, and `git diff --check`.
