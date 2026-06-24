## Why

`abnormal.json` already exercises some FlashDB error paths, but it allows `code` as an accepted difference. For L3 migration evidence, KVDB visible error semantics such as `status`, `code`, and `value` must be strict behavior fields, otherwise a migrated Rust API can silently drift while the diff still passes.

`abnormal.json` 已经覆盖了一部分 FlashDB 异常路径，但它把 `code` 放进 accepted differences。对 L3 迁移证据来说，KVDB 可见错误语义中的 `status`、`code`、`value` 必须是严格行为字段，否则 Rust 迁移后的 API 可能发生语义漂移但差分仍然通过。

## What Changes

- Add a named L3 slice, `kvdb-error-boundary`, under the existing FlashDB L3 migration loop.
- Freeze a deterministic KVDB fixture covering missing-key get, empty-key set, overlong-key set, and a valid post-error set/get sanity path.
- Generate Rust replay, WSL/Linux/CI C oracle, schema-aware diff, negative diff, compile self-healing, unsafe, cache, performance smoke, and bilingual summary evidence under `validation/evidence/flashdb/`.
- Explicitly forbid accepted differences for `status`, `code`, `value`, `key`, operation success, step ids, operation names, and error semantics.
- Keep error-message text as metadata when needed, while preserving machine-checkable error code and status parity.
- Keep single-writer patching; parallel agents are used only for read-only slice review, C oracle boundary review, evidence audit, and patch review.
- No breaking changes to public Rust API are intended.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `flashdb-l3-agent-migration-loop`: Add KVDB error-boundary behavior as a strict L3 slice, including C oracle parity, diff gates, evidence files, unsafe budget, cache invalidation, and bounded self-healing rules.

## Impact

- Rust fixture and tests under `flashDB_rust/fixtures/` and `flashDB_rust/tests/`.
- Existing Rust KVDB/replay code under `flashDB_rust/src/` only if tests expose a parity gap.
- Existing C oracle tooling under `flashDB_rust/oracle/`; no C oracle contract broadening is planned unless validation proves it is required.
- L3 evidence under `validation/evidence/flashdb/`.
- OpenSpec artifacts under `openspec/changes/run-flashdb-kvdb-error-boundary-l3-loop/`.
- No new runtime dependency, async runtime, or internal multithreading is planned.
