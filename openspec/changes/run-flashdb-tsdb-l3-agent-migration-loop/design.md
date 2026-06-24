## Context

FlashDB Rust already contains a seed TSDB implementation in `flashDB_rust/src/tsdb.rs`, replay support in `flashDB_rust/src/replay.rs`, and Rust tests for append/query/status/reopen behavior. The existing C oracle in `flashDB_rust/oracle/flashdb_c_oracle.c` supports `ts.append`, `ts.query`, `ts.set_status`, `ts.count_status`, `ts.reopen`, and `ts.image_hash`, which makes TSDB a lower-risk second L3 slice than KVDB compact/overwrite.

FlashDB Rust 当前已经有 `flashDB_rust/src/tsdb.rs` 的 TSDB 种子实现、`flashDB_rust/src/replay.rs` 的 replay 支持，以及 append/query/status/reopen 的 Rust 测试。现有 C oracle 已支持 `ts.append`、`ts.query`、`ts.set_status`、`ts.count_status`、`ts.reopen`、`ts.image_hash`，因此 TSDB 作为第二个 L3 切片比 KVDB compact/overwrite 风险更低。

The first L3 slice, `kvdb-lifecycle`, established the evidence format and safety boundary. This change reuses that format instead of inventing a new migration framework.

## Goals / Non-Goals

**Goals:**

- Freeze one named slice: `tsdb-append-query-status`.
- Preserve cross-file TSDB relationships between Rust public APIs, replay operations, fixtures, tests, C oracle operations, and evidence reports.
- Generate Rust replay and WSL/Linux/CI C oracle reports from the same fixture and compare them with schema-aware diff.
- Add targeted Rust tests and negative diff tests for behavior fields such as entries, timestamp, status, count, entry id, operation status, and error code.
- Keep first-party non-test unsafe at 0% for this slice.
- Reuse the compile self-healing evidence format from the KVDB L3 slice.

**Non-Goals:**

- Do not claim full FlashDB migration completeness.
- Do not claim byte-for-byte flash image layout equivalence.
- Do not add async runtime, internal multithreading, or concurrency behavior to FlashDB Rust logic.
- Do not broaden accepted differences to hide behavior mismatches.
- Do not refactor unrelated KVDB, flash, format, or CLI behavior unless required by this TSDB slice.

## Decisions

1. **Select TSDB before KVDB compact/overwrite.**
   TSDB has stronger current oracle coverage, while KVDB compact currently maps mostly to accepted image-hash metadata in the C oracle. The TSDB slice therefore gives better semantic evidence per unit of change.

2. **Use a new L3 fixture instead of extending `tsdb-basic.json` in place.**
   The fixture `flashDB_rust/fixtures/l3-tsdb-append-query-status.json` will make the evidence boundary explicit and avoid changing older smoke fixture semantics.

3. **Keep behavior fields non-ignorable.**
   Accepted differences may include metadata such as `image_hash`, `backend`, `toolchain_status`, `source`, `fixture`, `fixture_hash`, and `report_path`. They must not include `entries`, `entry_id`, `timestamp`, `status`, `value`, `count`, `code`, or operation success.

4. **Use bounded parallelism.**
   Parallel agents may review TSDB slice context, C oracle behavior, and evidence completeness. Code edits remain single-writer to avoid conflicting patches.

5. **Treat performance as smoke evidence only.**
   A short TSDB replay/stress command records operation count and elapsed time, but it cannot replace C/Rust semantic diff or Rust tests.

## Risks / Trade-offs

- **TSDB id mapping differs between Rust and C** -> The fixture uses deterministic append order and entry ids that both reports expose; diff fails if ids diverge.
- **Reverse time query semantics differ** -> The fixture includes forward and reversed query ranges and treats ordering as behavior.
- **Status update semantics drift** -> The fixture checks `ts.set_status` and `ts.count_status`; status/count cannot be accepted differences.
- **Local Windows lacks C toolchain** -> Local skip evidence records `SKIPPED_LOCAL_NO_C_TOOLCHAIN`, but L3 pass requires WSL/Linux/CI `C_ORACLE_GENERATED`.
- **Automatic repair could widen scope** -> PatchPlan evidence must reject changes that alter accepted differences, C oracle contract, public API outside the impact set, or unsafe budget.
