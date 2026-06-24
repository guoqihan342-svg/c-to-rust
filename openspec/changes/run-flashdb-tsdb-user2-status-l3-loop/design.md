## Context

The previous repair separated `ts.set_status` step outcome from TS business status by emitting `ts_status`. That makes status-heavy TSDB evidence safe to expand. Existing deleted-status evidence explicitly left `user2` out of scope, so `user2` is now a small, isolated follow-up slice.

上一轮修复已经把 `ts.set_status` 的步骤结果与 TS 业务状态分开，用 `ts_status` 输出业务状态。这样后续状态密集型 TSDB 证据可以安全扩展。现有 deleted-status 证据明确把 `user2` 排除在外，因此 `user2` 是一个小而独立的后续切片。

## Goals / Non-Goals

**Goals:**

- Validate `user2` as a public visible TSDB status through Rust replay and C oracle.
- Prove `ts.set_status user2` emits `ts_status:"user2"`.
- Prove `count_status user2` and `count_status written` remain stable across reopen.
- Prove schema-aware diff rejects a `user2` count or `ts_status` mutation.
- Preserve first-party non-test unsafe at 0%.

**Non-Goals:**

- Do not change TSDB storage behavior, query ordering, report schema, status enum values, or fixture input schema.
- Do not claim `fdb_tsl_clean`, physical deletion, GC, sector rollover/full, capacity pressure, corrupt-image reopen, byte-for-byte layout, payload limits, or power-loss behavior.
- Do not introduce async runtime, internal multithreading, or public API changes.

## Decisions

1. Use a dedicated `l3-tsdb-user2-status.json` fixture instead of extending deleted-status evidence.

   This keeps evidence attribution clean and avoids weakening the archived deleted-status slice with new behavior.

2. Keep query checks secondary and count/reopen checks primary.

   The public status behavior to freeze is `set_status user2` plus `count_status user2` before and after reopen. Query output can provide visibility but should not broaden the slice into query-order semantics.

3. Use `ts_status` as the strict business status field.

   The report-schema repair made `ts_status` the unambiguous field for successful `ts.set_status`. This slice depends on that contract and keeps it guarded by negative diff.

## Risks / Trade-offs

- C/Rust report order can differ for query entries -> Keep count semantics as the primary correctness gate and compare only behavior fields already normalized by the schema-aware diff.
- Historical evidence still marks `user2` as a gap -> Create new evidence rather than rewriting older archived summaries.
- If C oracle generation is unavailable locally -> Record skip as non-pass and require WSL/CI `C_ORACLE_GENERATED` before marking semantic equivalence.
