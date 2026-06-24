## Why

`tsdb-reverse-query-reopen` already has fixture, replay, diff, and evidence coverage, but the Rust replay test only checks the reopen step by `id` and `op`. The test should also assert the public step status, code, and image hash field so a malformed reopen report cannot pass unnoticed.

`tsdb-reverse-query-reopen` 已经具备 fixture、replay、diff 和证据覆盖，但 Rust replay 测试对 reopen step 只检查 `id` 和 `op`。测试应同时锁定 step status、code 和 image hash 字段，避免 reopen 报告结构退化时仍然通过。

## What Changes

- Harden the `l3_tsdb_reverse_query_reopen_fixture_replays_reverse_order` test.
- Assert `ts-rqr-006` contains `op:"ts.reopen"`, `status:"ok"`, `code:"OK"`, and `image_hash`.
- Record targeted test evidence for the hardening.
- Keep this as test-only work: no production code, fixture, C oracle, replay, or public API behavior changes.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `flashdb-l3-agent-migration-loop`: Add a focused test-evidence requirement for the TSDB reverse-query-reopen reopen step report fields.

## Impact

- `flashDB_rust/tests/differential_replay.rs`
- `openspec/specs/flashdb-l3-agent-migration-loop/spec.md` after archive
- New evidence under `validation/evidence/flashdb/tsdb-reverse-query-reopen-test-hardening-*`
