# FlashDB TSDB Deleted Status Reopen L3 Summary

## Result / 结果

- Status: passed
- Slice: `tsdb-deleted-status-reopen`
- Fixture: `flashDB_rust/fixtures/l3-tsdb-deleted-status-reopen.json`
- Fixture hash: `ee09075f` / sha256 `4f19d769450452177d68a78c4e5eb54877d5055d94472ea2ad1f06b7e750dcfb`
- Source commit: `93d175549da579b8abac07bd175ce4c3f9dde829`
- Repo commit at evidence generation: `76f35bfad6b0bffa96ce0d8dccb820dacf8e8c41`

This fixture validates public visible TSDB status-count behavior through reopen: append two entries, set entry 1 to `deleted`, require `deleted` count 1, require `written` count 1, reopen, then require `deleted` count 1 again.

该 fixture 验证 TSDB 公开可见的状态计数与 reopen 持久化行为：追加两条记录，将 entry 1 设置为 `deleted`，要求 `deleted` 计数为 1，`written` 计数为 1，reopen 后再次要求 `deleted` 计数为 1。

## Evidence / 证据

- C oracle: `C_ORACLE_GENERATED` via producer marker `C_ORACLE_GENERATED`
- Schema diff: `passed`, first_mismatch ``
- Negative diff: `failed` at `steps.ts-del-007.count`
- Cargo check JSON: `passed`, errors `0`
- Unsafe: count `0`, ratio `0`
- Performance smoke: secondary-only `true`, elapsed_ms `374`

Accepted metadata differences are limited to `image_hash,backend,toolchain_status,source,fixture,fixture_hash,report_path`. Behavior fields such as `entry_id`, `timestamp`, `status`, `value`, `count`, step status, step code, operation id, operation name, operation success, and error semantics are forbidden differences.

accepted differences 只允许包含 `image_hash,backend,toolchain_status,source,fixture,fixture_hash,report_path` 这些元数据字段。`entry_id`、`timestamp`、`status`、`value`、`count`、step status、step code、operation id、operation name、operation success 和 error semantics 等行为字段禁止被忽略。

## Non-Goals / 非目标

- Does not claim `fdb_tsl_clean` or physical deletion behavior.
- Does not claim deleted records are included or excluded from `ts.query` results.
- Does not claim byte-for-byte flash image layout, sector rollover/full, power-loss, capacity-pressure, non-monotonic timestamp, payload limit, `user2`, or TSDB error-boundary behavior.
- Does not introduce async runtime, internal multithreading, or concurrency changes.
- Known gap: current `ts.set_status` report JSON uses duplicate `status` keys, so this slice does not claim schema-level separation of step status and entry status.

中文说明：本切片不声明 `fdb_tsl_clean`、物理删除、deleted 记录是否出现在 `ts.query`、字节级布局、扇区滚转/full、掉电、容量压力、非单调时间戳、payload 上限、`user2` 或 TSDB 错误边界行为；也不引入 async runtime、内部多线程或并发改动。已知缺口是当前 `ts.set_status` 报告 JSON 存在重复 `status` key，因此本切片不声明 step status 与 entry status 已在 schema 层清晰分离。

## Next Slice / 下一切片

Recommended next: `kvdb-delete-invalid-key` if continuing KVDB error-boundary expansion, or `tsdb-error-boundary` if expanding TSDB public API error behavior.

下一步建议：如果继续扩展 KVDB 错误边界，选择 `kvdb-delete-invalid-key`；如果继续扩展 TSDB 公开 API 错误行为，选择 `tsdb-error-boundary`。
