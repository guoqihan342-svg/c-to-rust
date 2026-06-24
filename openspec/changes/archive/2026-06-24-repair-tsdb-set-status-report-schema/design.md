## Context

FlashDB L3 evidence already covers TSDB append/query/status, deleted status reopen, and error-boundary behavior. These slices repeatedly noted a report-schema gap: successful `ts.set_status` steps encode both the step execution state and requested TS status under the same JSON key `status`.

FlashDB L3 已覆盖 TSDB append/query/status、deleted status reopen 和 error-boundary。多个切片都记录了同一个 schema 缺口：成功的 `ts.set_status` step 同时把 step 执行状态和请求的 TS 状态写入同名 JSON key `status`。

## Goals / Non-Goals

**Goals:**

- Keep step execution status as `status` and code as `code`.
- Rename only the business TS status field on successful `ts.set_status` reports to `ts_status`.
- Keep Rust replay and C oracle report schemas byte-for-byte comparable for behavior fields.
- Preserve schema-aware diff protection so `ts_status` cannot be hidden by accepted differences.
- Prove the repair with TDD red/green evidence and final validation.

**Non-Goals:**

- Do not change `TsDb::set_status`, persistence, status enum values, query ordering, C FlashDB behavior, or accepted-difference metadata policy.
- Do not introduce async runtime, internal multithreading, or a new JSON dependency.
- Do not rewrite older archived evidence files unless a current test fixture or checked-in expected report requires the schema change.

## Decisions

1. Use `ts_status` for the business TS status field.

   `entry_status` could be misread as a status attached to a returned entry, while `ts_status` mirrors the operation domain and is short enough for fixtures and C oracle output. `status` remains the step-level execution state.

2. Update both Rust replay and C oracle in the same change.

   If only Rust changes, schema-aware C/Rust diff would fail on status-heavy fixtures. Keeping both emitters aligned makes the repair useful for future L3 slices.

3. Use TDD at the test boundary.

   Add or tighten a replay test that rejects duplicate `"status"` on `ts.set_status` before production edits, then implement the minimal emitter rename and update expected fixtures.

4. Treat this as a schema repair, not a new TSDB semantic slice.

   The behavior value remains `user1`, `deleted`, or another TS status. The change only clarifies where the value is stored in the report JSON.

## Risks / Trade-offs

- Existing archived evidence still contains the old duplicate key shape -> Leave archived evidence immutable and document that this repair affects new reports only.
- External consumers may read `status` for TS business state -> `status` was already ambiguous and invalid as a stable business field; the repaired contract is `ts_status`.
- Manual JSON formatting can reintroduce duplicate keys -> Add direct tests for `ts.set_status` output and schema diff behavior.
