## 1. Slice Contract / 切片合同

- [x] 1.1 Freeze the `kvdb-lifecycle` L3 slice with C API list, Rust module list, fixture path, FlashDB source commit, backend matrix, and accepted-difference policy.
- [x] 1.2 Produce `validation/evidence/flashdb/l3-kvdb-lifecycle-context-pack.json` with C callers/callees, Rust public APIs, related tests, oracle contract, unsafe status, cache key, and rollback id.
- [x] 1.3 Record the implementation impact set before any public API or cross-module signature change.
- [x] 1.4 Assign bounded agent roles for C slice review, Rust API review, oracle/diff review, self-healing review, and evidence audit; keep code patching single-writer.

## 2. Fixture And Oracle / Fixture 与 Oracle

- [x] 2.1 Add or freeze a deterministic `kvdb-lifecycle` fixture covering set, get, delete, missing get, reopen, and stable entry/report fields.
- [x] 2.2 Extend Rust replay/report generation only where the slice requires new fields or operations.
- [x] 2.3 Generate the Rust replay report at `validation/evidence/flashdb/l3-kvdb-lifecycle-rust-report.json`.
- [x] 2.4 Generate the C oracle report at `validation/evidence/flashdb/l3-kvdb-lifecycle-c-oracle.json` on Linux/WSL/CI with `toolchain_status == C_ORACLE_GENERATED`.
- [x] 2.5 Record `SKIPPED_LOCAL_NO_C_TOOLCHAIN` when running on local Windows without a C compiler, and do not count that marker as L3 pass evidence.

## 3. TDD And Semantic Diff / 测试驱动与语义差分

- [x] 3.1 Add Rust integration tests for the selected KVDB lifecycle path before changing implementation behavior.
- [x] 3.2 Add a negative regression fixture or report mutation that must fail schema-aware diff.
- [x] 3.3 Implement or adjust the minimal Rust slice behavior needed for C/Rust report parity without weakening existing tests.
- [x] 3.4 Run schema-aware diff and write `validation/evidence/flashdb/l3-kvdb-lifecycle-diff.json`.
- [x] 3.5 Verify that accepted differences exclude behavior fields such as value, status, count, operation success, and error semantics.

## 4. Compile Self-Healing / 编译自愈

- [x] 4.1 Run `cargo check --message-format=json` for `flashDB_rust` and write `validation/evidence/flashdb/l3-kvdb-lifecycle-rust-check.json`.
- [x] 4.2 Parse rustc JSON into `error-events.jsonl` with code, primary span, related spans, rendered message, root cause key, affected items, and rerun command.
- [x] 4.3 Implement rule-first classifiers for API/type/borrow/module/test/diff/oracle/environment/evidence-gap failures.
- [x] 4.4 Record every automatic repair attempt in `patches.jsonl` with patch id, files, spans, reason, expected error delta, risk, rollback id, forbidden changes, AI usage, and verification commands.
- [x] 4.5 Enforce retry limit and rollback when a root cause repeats, introduces a new error category, widens unsafe, changes oracle/golden contract, or creates semantic diff mismatch.

## 5. Safety, Cache, And Performance / 安全、缓存与性能

- [x] 5.1 Run unsafe scan and write unsafe count, unsafe ratio, scanned files, ignored paths, and ledger entries into L3 evidence.
- [x] 5.2 Keep first-party non-test unsafe at 0% for the initial slice; if unsafe becomes unavoidable, add ledger entries and require explicit review before pass.
- [x] 5.3 Add cache metadata for ContextPack and self-healing outputs keyed by source commit, file hashes, Cargo.lock, command args, rustc version, feature/env, and context schema.
- [x] 5.4 Run performance smoke for the slice and write backend, operation counters, elapsed time, command, and toolchain status to `validation/evidence/flashdb/l3-kvdb-lifecycle-performance-smoke.json`.
- [x] 5.5 Do not introduce async runtime, internal multithreading, or concurrency changes to FlashDB Rust logic unless a design update and performance evidence justify it.

## 6. Verification And Reporting / 验证与报告

- [x] 6.1 Run `cargo fmt -- --check` in `flashDB_rust`.
- [x] 6.2 Run `cargo check` and `cargo test` in `flashDB_rust`.
- [x] 6.3 Run CLI replay, schema diff, unsafe scan, and short stress for the selected fixture.
- [x] 6.4 Run Linux/WSL/CI C oracle generation and C/Rust diff before marking L3 semantic evidence passed.
- [x] 6.5 Write `validation/evidence/flashdb/l3-kvdb-lifecycle-summary.json` and a short bilingual summary documenting slice scope, commands, evidence paths, unsafe ratio, accepted differences, failures, and next slice recommendation.
- [x] 6.6 Run `openspec validate run-flashdb-l3-agent-migration-loop --strict`, `openspec validate --all`, and `git diff --check`.
