# FlashDB TSDB Set Status Report Schema Summary

## Result / 结果

- Status: passed
- Slice: `tsdb-set-status-report-schema`
- Fixture: `flashDB_rust/fixtures/l3-tsdb-set-status-report-schema.json`
- Fixture hash: `bd8c4ede`
- Source commit: `93d175549da579b8abac07bd175ce4c3f9dde829`

This repair keeps step execution status as `status:"ok"` and moves the TSDB business status on successful `ts.set_status` steps to `ts_status:"user1"` or the corresponding TS status value.

本次修复保留步骤执行状态字段 `status:"ok"`，并将成功 `ts.set_status` step 的 TSDB 业务状态移动到 `ts_status:"user1"` 或对应的 TS 状态值。

## Evidence / 证据

- TDD red: focused test failed because `ts_status` was missing.
- TDD green: focused test passed after Rust replay emitted `ts_status`.
- C oracle: `C_ORACLE_GENERATED` report uses `ts_status`.
- Schema diff: passed with `first_mismatch:null`.
- Negative diff: failed as expected at `steps.ts-schema-002.ts_status`.
- Cargo check: passed with 0 errors and 0 warnings; automatic repair was not needed.
- Unsafe: first-party non-test unsafe count is 0.
- Performance smoke: secondary-only, elapsed_ms `406`.

## Non-Goals / 非目标

- Does not change TSDB storage, query ordering, count semantics, FlashDB C behavior, or fixture input schema.
- Does not rename query entry `status`; only successful `ts.set_status` business status is separated as `ts_status`.
- Does not widen accepted differences to hide `status`, `code`, `entry_id`, `op`, `id`, or `ts_status`.
- Does not introduce async runtime, internal multithreading, or unsafe code.

本切片不改变 TSDB 存储、query 顺序、count 语义、FlashDB C 行为或 fixture 输入 schema；不重命名 query entry 内的 `status`；不扩大 accepted differences；也不引入 async runtime、内部多线程或 unsafe。
