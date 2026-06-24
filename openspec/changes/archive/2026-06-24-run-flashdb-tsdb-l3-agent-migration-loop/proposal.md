## Why

The first FlashDB L3 slice proved the bounded agent loop for `kvdb-lifecycle`, but the Rust migration still has no L3 semantic evidence for TSDB behavior. TSDB append, query, status updates, count-by-status, and reopen are a good second slice because the existing C oracle already supports these operations and the scope stays small enough for single-point progressive refactoring.

第一个 FlashDB L3 切片已经验证了 `kvdb-lifecycle` 的有边界智能体迁移闭环，但 Rust 迁移还没有 TSDB 行为的 L3 语义证据。TSDB append/query/status/count/reopen 是合适的第二个切片，因为现有 C oracle 已支持这些操作，且范围足够小，适合继续做单点渐进式重构。

## What Changes

- Add a second named L3 slice, `tsdb-append-query-status`, under the existing FlashDB L3 migration loop.
- Freeze a deterministic TSDB fixture covering append, query, reversed query, status update, count-by-status, reopen, and invalid status/id regressions where practical.
- Generate Rust replay, C oracle, schema-aware diff, compile self-healing, unsafe, performance smoke, and bilingual summary evidence under `validation/evidence/flashdb/`.
- Keep automatic patching bounded: one writer applies code edits, while parallel agents perform read-only slice review, oracle review, and evidence audit.
- Preserve the existing rule that performance evidence is secondary to semantic equivalence and tests.
- No breaking changes to public Rust API are intended.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `flashdb-l3-agent-migration-loop`: Add TSDB append/query/status as the next L3 slice, including C oracle parity, diff gates, evidence files, unsafe budget, and bounded self-healing rules.

## Impact

- Rust implementation and tests under `flashDB_rust/src/`, `flashDB_rust/tests/`, and `flashDB_rust/fixtures/`.
- C oracle and local/WSL oracle generation under `flashDB_rust/oracle/`.
- L3 evidence under `validation/evidence/flashdb/`.
- OpenSpec artifacts under `openspec/changes/run-flashdb-tsdb-l3-agent-migration-loop/`.
- No new runtime dependency, async runtime, or internal multithreading is planned for FlashDB Rust logic.
