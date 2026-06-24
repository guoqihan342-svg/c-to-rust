## Context

The first TSDB L3 slice already includes reverse query before reopen and forward query after reopen. It does not isolate whether reverse query ordering remains stable after the file-backed TSDB is reopened. This slice adds that missing public-visible behavior without changing storage, replay schema, report schema, or query algorithms.

第一轮 TSDB L3 切片已经包含 reopen 前反向 query 和 reopen 后正向 query，但没有单独证明 file-backed TSDB reopen 后反向 query 顺序仍然稳定。本切片补齐这个公开可见行为，不改变存储、replay schema、报告 schema 或 query 算法。

## Goals / Non-Goals

**Goals:**

- Validate reverse `ts.query` ordering before and after reopen through Rust replay and C oracle.
- 通过 Rust replay 和 C oracle 验证 reopen 前后的反向 `ts.query` 顺序。
- Prove entry id, timestamp, TS status, payload value, operation id, operation name, step status, and step code remain strict behavior fields.
- 证明 entry id、timestamp、TS status、payload value、operation id、operation name、step status 和 step code 都是严格行为字段。
- Preserve first-party non-test unsafe at 0%.
- 保持一方非测试 Rust unsafe 为 0%。

**Non-Goals:**

- Do not change TSDB storage behavior, replay input schema, report schema, public APIs, C oracle semantics, or accepted-difference policy.
- 不改变 TSDB 存储行为、replay 输入 schema、报告 schema、公共 API、C oracle 语义或 accepted-difference 策略。
- Do not claim reverse `count_status` semantics, capacity exhaustion, sector rollover/full, clean/GC, physical deletion, corrupt-image reopen, byte-for-byte layout, payload limits, non-monotonic timestamps, async/threading, or power-loss behavior.
- 不声明反向 `count_status` 语义、容量耗尽、sector rollover/full、clean/GC、物理删除、损坏镜像 reopen、字节级布局、payload limit、非递增时间戳、异步/多线程或断电行为。

## Decisions

1. Use a dedicated `l3-tsdb-reverse-query-reopen.json` fixture.

   This avoids mutating the older append/query/status fixture and keeps the new evidence scoped to reverse ordering after reopen.

2. Use three monotonically increasing timestamps and one status update.

   Three entries make reverse ordering obvious: `30 -> 20 -> 10`. Updating the middle entry to `user1` also proves status preservation within the reversed entries without adding count behavior to the slice.

3. Include reverse query both before and after reopen.

   The before-reopen query establishes the intended order in the same fixture. The after-reopen query is the new behavior gate.

4. Mutate the after-reopen reverse query order for the negative diff.

   Changing the final query entries from reverse order to forward order should fail at the query `entries` behavior field, proving ordering cannot be accepted as metadata.

## Risks / Trade-offs

- C FlashDB and Rust seed layout can differ -> Keep image/layout metadata under accepted differences and keep query entries strict.
- C FlashDB 与 Rust seed layout 可能不同 -> 只接受 image/layout metadata 差异，query entries 保持严格。
- Reverse `count_status` might not have the same C/Rust boundary as reverse query -> Keep reverse count out of this slice.
- 反向 `count_status` 可能和反向 query 的 C/Rust 边界不同 -> 本切片排除反向 count。
- Non-monotonic timestamps are tempting but would change append semantics -> Keep timestamps monotonic and defer non-monotonic/error behavior to another slice.
- 非递增 timestamp 很有吸引力，但会改变 append 语义 -> 本切片保持 timestamp 单调递增，把非递增/错误行为留到后续切片。
