## Context

The previous TSDB payload-boundary slice validates empty payloads and exactly 128-byte ASCII payloads, including query/count visibility and reopen persistence. It deliberately does not validate what happens when the payload is larger than FlashDB's configured TSDB blob size. C FlashDB rejects over-limit TSDB payload writes with `FDB_WRITE_ERR`; the Rust migration harness needs the same public-visible error semantics before larger TSDB paths are trusted.

上一片 TSDB payload-boundary 已经验证空 payload 与刚好 128 字节 ASCII payload，包括 query/count 可见性与 reopen 持久性。它有意不验证 payload 超过 FlashDB 配置的 TSDB blob 大小时会发生什么。C FlashDB 会用 `FDB_WRITE_ERR` 拒绝超限 TSDB payload 写入；Rust 迁移 harness 在继续扩大 TSDB 路径前，需要对齐这个公开可见错误语义。

## Goals / Non-Goals

**Goals:**

- Validate one 129-byte ASCII `ts.append` failure through Rust replay and C oracle.
- 通过 Rust replay 与 C oracle 验证一条 129 字节 ASCII `ts.append` 失败。
- Prove the failed append reports `status:"error"` and `code:"FDB_WRITE_ERR"`.
- 证明失败 append 报告 `status:"error"` 与 `code:"FDB_WRITE_ERR"`。
- Prove the failed append does not create a visible TSDB record, does not consume a successful `entry_id`, and does not corrupt later successful append/query/count/reopen behavior.
- 证明失败 append 不产生可见 TSDB 记录、不消耗成功记录的 `entry_id`，且不破坏后续成功 append/query/count/reopen 行为。
- Keep first-party non-test unsafe at 0%.
- 保持一方非测试 Rust unsafe 为 0%。

**Non-Goals:**

- Do not validate binary or NUL payload handling, payloads larger than 129 bytes, capacity pressure, sector rollover/full, clean/GC, physical deletion, corrupt-image reopen, byte-for-byte layout, non-monotonic timestamps, async/threading, or power-loss behavior.
- 不验证 binary/NUL payload、超过 129 字节 payload、容量压力、sector rollover/full、clean/GC、物理删除、损坏镜像 reopen、字节级布局、非递增 timestamp、异步/多线程或断电行为。
- Do not change the replay fixture schema unless existing operations cannot express the behavior.
- 除非现有 operation 无法表达该行为，否则不改变 replay fixture schema。

## Decisions

1. Use a dedicated `l3-tsdb-over-limit-payload-error.json` fixture.

   This keeps the over-limit error boundary separate from the 128-byte success boundary and makes negative diff evidence easier to inspect.

   使用独立 `l3-tsdb-over-limit-payload-error.json` fixture。这样可以把超限错误边界与 128 字节成功边界分开，也让 negative diff 证据更容易检查。

2. Use one 129-byte ASCII payload.

   A single byte over the configured 128-byte limit is the smallest behavior delta. It avoids claiming broader payload-size classes while still proving the public error boundary.

   使用一条 129 字节 ASCII payload。刚超过配置的 128 字节限制 1 字节，是最小行为差异；它不声明更大 payload 类别，却能证明公开错误边界。

3. Keep strict behavior fields broad for this slice.

   Step status, step code, operation id/name, `entry_id`, timestamp, query entries, counts, and error semantics are behavior. Only layout/toolchain/source metadata can remain accepted differences.

   本切片保持较宽的严格行为字段。step status、step code、operation id/name、`entry_id`、timestamp、query entries、counts 与 error semantics 都是行为字段；只有 layout/toolchain/source metadata 可以继续作为 accepted differences。

4. Use a negative diff that mutates error behavior or visibility.

   The strongest small mutation is changing the over-limit append from `error/FDB_WRITE_ERR` to `ok/OK`, or making the rejected payload appear in query entries. Either must fail the schema-aware diff.

   negative diff 使用错误行为或可见性篡改。最小且强的篡改是把超限 append 从 `error/FDB_WRITE_ERR` 改为 `ok/OK`，或让被拒绝 payload 出现在 query entries 中；两者都必须被 schema-aware diff 拦截。

## Risks / Trade-offs

- Existing Rust replay may not enforce the 128-byte TSDB payload limit -> add the focused red test first, then patch only the append path if needed.
- 现有 Rust replay 可能尚未强制 128 字节 TSDB payload 限制 -> 先添加聚焦红测；如需要，只补 append 路径。
- Existing C oracle may not serialize failed append steps -> inspect and minimally extend the C oracle to preserve `FDB_WRITE_ERR` as a strict behavior code.
- 现有 C oracle 可能尚未序列化失败 append step -> 检查并最小扩展 C oracle，保留 `FDB_WRITE_ERR` 作为严格行为 code。
- Error diagnostics may differ between C and Rust -> keep free-form message text out of strict behavior, but do not accept status or code differences.
- C 与 Rust 的错误诊断文本可能不同 -> 自由文本 message 不作为严格行为，但 status/code 差异不能被接受。
