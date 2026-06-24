## Context

The previous TSDB slices validated append/query/status, deleted status, `user2`, error boundaries, and repeated status transitions. They do not yet prove that boundary payload lengths remain public-visible and persistent across C/Rust replay, especially the C oracle's configured `ORACLE_TSL_MAX_LEN=128` limit.

前几轮 TSDB 切片已经验证 append/query/status、deleted status、`user2`、错误边界和连续状态转换，但还没有证明 payload 长度边界在 C/Rust replay 中保持公开可见且可持久化，尤其是 C oracle 配置的 `ORACLE_TSL_MAX_LEN=128` 上限。

## Goals / Non-Goals

**Goals:**

- Validate an empty TSDB payload and an exactly 128-byte ASCII payload through Rust replay and C oracle.
- 通过 Rust replay 和 C oracle 验证空 TSDB payload 与刚好 128 字节 ASCII payload。
- Prove full-range query, exact timestamp query, empty range query, count-by-status, reopen, and query-after-reopen preserve visible payload behavior.
- 证明全范围 query、精确时间戳 query、空范围 query、按状态计数、reopen 和 reopen 后 query 都保持 payload 可见行为。
- Prove payload value differences are behavior differences in schema-aware diff.
- 证明 payload value 差异属于 schema-aware diff 的行为差异。
- Preserve first-party non-test unsafe at 0%.
- 保持一方非测试 Rust unsafe 为 0%。

**Non-Goals:**

- Do not change TSDB storage behavior, replay input schema, report schema, public APIs, C oracle semantics, or accepted-difference policy.
- 不改变 TSDB 存储行为、replay 输入 schema、报告 schema、公共 API、C oracle 语义或 accepted-difference 策略。
- Do not claim over-limit payload rejection, binary or NUL payload handling, capacity exhaustion, sector rollover/full, clean/GC, physical deletion, corrupt-image reopen, byte-for-byte layout, non-monotonic timestamps, or power-loss behavior.
- 不声明超限 payload 拒绝、二进制或 NUL payload 处理、容量耗尽、sector rollover/full、clean/GC、物理删除、损坏镜像 reopen、字节级布局、非递增时间戳或断电行为。
- Do not introduce async runtime, internal multithreading, or unsafe code.
- 不引入异步运行时、内部多线程或 unsafe 代码。

## Decisions

1. Use a dedicated `l3-tsdb-payload-boundary.json` fixture.

   This keeps payload-boundary evidence separate from status-transition and error-boundary slices, and lets future over-limit failure work become a separate small slice.

2. Use ASCII payloads only.

   Rust replay currently treats fixture values as UTF-8 strings and reports values as JSON strings. ASCII keeps this slice focused on boundary length rather than encoding, escaping, or binary/NUL transport.

3. Use an exactly 128-byte payload as the success boundary.

   The C oracle initializes TSDB with `ORACLE_TSL_MAX_LEN=128`, so a 128-byte ASCII payload is the largest success case this slice should claim. A 129-byte rejection path remains out of scope until C/Rust error semantics are designed and verified.

4. Treat query entry `value`, append `value`, entry ids, timestamps, statuses, counts, step status, step code, operation success, operation id, and operation name as strict behavior fields.

   The slice is about public visible payload behavior. Only metadata such as image hash, backend, source, fixture path, fixture hash, report path, local toolchain status, or diagnostic message text may remain accepted differences where existing diff policy already allows it.

## Risks / Trade-offs

- C FlashDB and Rust seed layout can differ -> Keep image/layout metadata under accepted differences and keep payload/query/count fields strict.
- C FlashDB 与 Rust seed layout 可能不同 -> 只接受 image/layout metadata 差异，payload/query/count 字段保持严格。
- A 128-byte payload could expose toolchain-specific C behavior -> Generate durable `C_ORACLE_GENERATED` evidence and downgrade only if the C oracle itself rejects the success boundary.
- 128 字节 payload 可能暴露工具链相关的 C 行为 -> 生成持久化 `C_ORACLE_GENERATED` 证据；只有 C oracle 自身拒绝成功边界时才降级。
- Binary payload support is tempting but broadens JSON/replay encoding semantics -> Keep binary/NUL payloads out of this slice.
- 二进制 payload 支持很有吸引力，但会扩大 JSON/replay 编码语义 -> 本切片排除 binary/NUL payload。
- Capacity and sector rollover are larger layout slices -> Do not use this payload fixture to infer storage fullness, sector movement, or GC behavior.
- 容量与 sector rollover 是更大的布局切片 -> 不用本 payload fixture 推断存储满、sector 迁移或 GC 行为。
