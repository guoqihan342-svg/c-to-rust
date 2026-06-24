## Why

TSDB L3 evidence already covers append/query/status, deleted status reopen, error boundaries, and the `ts.set_status` report-schema repair. The remaining small status gap is `user2`, which is a public FlashDB TS status value but has not yet been validated through a C/Rust oracle loop.

TSDB L3 证据已经覆盖 append/query/status、deleted status reopen、错误边界，以及 `ts.set_status` report-schema 修复。剩下的最小状态缺口是 `user2`：它是 FlashDB 公开 TS 状态值，但尚未通过 C/Rust oracle 闭环验证。

## What Changes

- Add a focused `tsdb-user2-status` L3 fixture that appends records, sets one entry to `user2`, counts `user2` and `written`, reopens, and recounts `user2`.
- Add Rust replay/differential tests proving `ts_status:"user2"` is emitted and `user2` counts are stable before and after reopen.
- Generate C oracle, Rust report, schema diff, and negative diff evidence for the same fixture.
- Keep `user2`, count, step status, step code, operation id/name, and operation success as strict behavior fields.
- Do not claim capacity exhaustion, sector full, clean/GC, physical deletion, byte-for-byte layout, corrupt-image reopen, payload limits, or power-loss behavior.

## Capabilities

### New Capabilities

### Modified Capabilities

- `flashdb-l3-agent-migration-loop`: add TSDB `user2` public status behavior as a focused L3 C/Rust replay slice.

## Impact

- `flashDB_rust/fixtures/l3-tsdb-user2-status.json`
- `flashDB_rust/tests/differential_replay.rs`
- `validation/evidence/flashdb/l3-tsdb-user2-status-*`
- `openspec/specs/flashdb-l3-agent-migration-loop/spec.md` after archive

No public Rust API, storage layout, C FlashDB source, async runtime, threading model, or unsafe policy change is intended.
