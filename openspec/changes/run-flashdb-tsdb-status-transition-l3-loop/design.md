## Context

The previous TSDB slices validated individual statuses and the repaired `ts_status` report field. They do not yet prove that repeated `ts.set_status` calls on the same entry leave only the latest public status visible through count/query and reopen.

前几轮 TSDB 切片已经验证了单个状态和修复后的 `ts_status` 报告字段，但还没有证明同一 entry 上连续 `ts.set_status` 后，只有最新公共状态会通过 count/query 和 reopen 可见。

## Goals / Non-Goals

**Goals:**

- Validate repeated TSDB status transitions on one entry through Rust replay and C oracle.
- 验证同一 TS entry 的连续状态转换在 Rust replay 和 C oracle 中一致。
- Prove `user1` and `user2` intermediate statuses are no longer counted after the entry moves to `deleted`.
- 证明 entry 转为 `deleted` 后，中间态 `user1` 和 `user2` 不再被计数。
- Prove query reports the final `deleted` status and a second entry remains `written`.
- 证明 query 显示最终 `deleted` 状态，且另一条 entry 仍为 `written`。
- Prove reopen preserves the latest visible statuses.
- 证明 reopen 后最新可见状态保持不变。
- Preserve first-party non-test unsafe at 0%.
- 保持一方非测试 Rust unsafe 为 0%。

**Non-Goals:**

- Do not change TSDB storage behavior, replay input schema, report schema, status enum values, query ordering, public APIs, or C oracle semantics.
- 不改变 TSDB 存储行为、replay 输入 schema、报告 schema、状态枚举值、query 排序、公共 API 或 C oracle 语义。
- Do not claim `fdb_tsl_clean`, physical deletion, GC, sector rollover/full, capacity pressure, corrupt-image reopen, byte-for-byte layout, payload limits, or power-loss behavior.
- 不声明 `fdb_tsl_clean`、物理删除、GC、sector rollover/full、容量压力、损坏镜像 reopen、字节级布局、payload limit 或断电行为。
- Do not introduce async runtime, internal multithreading, or unsafe code.
- 不引入异步运行时、内部多线程或 unsafe 代码。

## Decisions

1. Use a dedicated `l3-tsdb-status-transition.json` fixture.

   This keeps repeated status-transition evidence separate from the `deleted`, `user2`, and report-schema slices.

2. Use two entries: one entry transitions `written -> user1 -> user2 -> deleted`, and one entry stays `written`.

   This makes the expected counts precise: final `deleted` is 1, final `written` is 1, and intermediate `user1`/`user2` counts are 0.

3. Treat count/query/reopen as strict behavior fields and metadata as the only accepted difference.

   The slice is about public visible state. Differences in `count`, query entry `status`, `entry_id`, `timestamp`, `value`, step `status`, step `code`, `op`, or `id` must fail.

## Risks / Trade-offs

- C FlashDB and Rust seed layout can differ -> Keep layout metadata under accepted differences and keep behavior fields strict.
- C FlashDB 与 Rust seed layout 可能不同 -> 只接受 layout metadata 差异，行为字段保持严格。
- Capacity and sector behavior are tempting next targets but require layout/toolchain-specific control -> Keep them out of this slice.
- 容量和 sector 行为很像下一目标，但需要 layout/toolchain 控制 -> 本切片明确排除。
- Query output contains nested entries -> Use full-output string assertions or schema diff, not the flat `step_json_for` helper for query entries.
- query 输出包含嵌套 entries -> 对 query 使用完整输出片段或 schema diff，不用只适合扁平 step 的 `step_json_for`。
