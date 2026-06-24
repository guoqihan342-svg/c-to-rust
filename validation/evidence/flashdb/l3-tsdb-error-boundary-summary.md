# FlashDB TSDB Error Boundary L3 Summary

## Result / 结果

- Status: passed
- Slice: `tsdb-error-boundary`
- Fixture: `flashDB_rust/fixtures/l3-tsdb-error-boundary.json`
- Fixture hash: `a67cc63c` / sha256 `2d48fefdea2e1c3b35c1fc4139a547062196cf8af84d059eae4ec90e12a7ee69`
- Source commit: `93d175549da579b8abac07bd175ce4c3f9dde829`

This fixture validates public visible TSDB error-boundary behavior: a valid append, unknown `entry_id` returning `INVALID_RANGE`, unknown status returning `PARSE`, invalid timestamp returning `PARSE`, missing query range returning `PARSE`, and valid append/query behavior after those errors.

该 fixture 验证 TSDB 公开可见的错误边界行为：先执行有效 append，再验证未知 `entry_id` 返回 `INVALID_RANGE`，未知状态返回 `PARSE`，非法 timestamp 返回 `PARSE`，缺失 query 范围字段返回 `PARSE`，并验证这些错误之后仍可继续执行有效 append/query。

## Evidence / 证据

- C oracle: `C_ORACLE_GENERATED` via producer marker `C_ORACLE_GENERATED`
- Schema diff: `passed`, first_mismatch ``
- Negative diff: `failed` at `steps.ts-eb-002.code`
- Cargo check JSON: `passed`, errors `0`
- Unsafe: count `0`, ratio `0`
- Performance smoke: secondary-only `true`, elapsed_ms `158`

Accepted metadata differences are limited to `image_hash,message,backend,toolchain_status,source,fixture,fixture_hash,report_path`. Behavior fields such as `status`, `code`, `entry_id`, `timestamp`, `value`, `count`, `entries`, step status, step code, operation id, operation name, operation success, and error semantics are forbidden differences.

accepted differences 只允许包含 `image_hash,message,backend,toolchain_status,source,fixture,fixture_hash,report_path` 这些元数据或诊断字段。`status`、`code`、`entry_id`、`timestamp`、`value`、`count`、`entries`、step status、step code、operation id、operation name、operation success 和 error semantics 等行为字段禁止被忽略。

## Non-Goals / 非目标

- Does not claim TSDB capacity exhaustion, sector full, clean, GC, physical deletion, corrupt-image reopen, byte-for-byte layout, or power-loss behavior.
- Does not claim payload maximum length or arbitrary binary payload behavior.
- Does not treat `ts.query` with `from > to` as an error.
- Does not use exact diagnostic `message` text as a correctness gate.
- Does not introduce async runtime, internal multithreading, or concurrency changes.
- Known gap: successful `ts.set_status` report JSON still uses duplicate `status` keys, so this slice avoids relying on successful `ts.set_status` output.

中文说明：本切片不声明 TSDB 容量耗尽、sector full、clean、GC、物理删除、损坏镜像 reopen、字节级布局或掉电行为；不声明 payload 最大长度或任意二进制 payload；不把 `from > to` 的 `ts.query` 当成错误；不把精确 `message` 文本作为正确性门禁；也不引入 async runtime、内部多线程或并发改动。已知缺口是成功 `ts.set_status` 报告 JSON 仍存在重复 `status` key，因此本切片避开成功 `ts.set_status` 输出。

## Next Slice / 下一切片

Recommended next: start a separate layout-aware TSDB capacity-pressure slice only if capacity semantics become the priority, or clean up the `ts.set_status` report schema before expanding status-heavy TSDB evidence.

下一步建议：只有当容量语义成为优先级时，才单独启动 layout-aware 的 TSDB capacity-pressure 切片；否则先清理 `ts.set_status` 报告 schema，再扩展更多状态相关 TSDB 证据。
