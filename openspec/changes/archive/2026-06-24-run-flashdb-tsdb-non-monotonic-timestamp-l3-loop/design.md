## Context

Current TSDB L3 evidence covers successful append/query/status behavior, reverse query order, payload boundaries, and over-limit payload rejection. The main remaining append-order gap is the upstream FlashDB rule in `tsl_append`: `cur_time <= db->last_time` returns `FDB_WRITE_ERR` and the TSL is dropped. Rust `TsDb::append` currently checks payload length but does not enforce timestamp ordering, so a focused red/green slice can close a real C/Rust semantic gap without broadening the migration surface.

当前 TSDB L3 证据已经覆盖成功 append/query/status 行为、反向 query 顺序、payload 边界和超限 payload 拒绝。剩余的主要 append 顺序缺口是上游 FlashDB 在 `tsl_append` 中的规则：`cur_time <= db->last_time` 会返回 `FDB_WRITE_ERR`，并丢弃该 TSL。Rust `TsDb::append` 当前检查 payload 长度，但没有强制 timestamp 顺序，因此一个聚焦的红/绿切片可以关闭真实的 C/Rust 语义缺口，同时不扩大迁移面。

## Goals / Non-Goals

**Goals:**

- Validate duplicate timestamp and decreasing timestamp append failures through Rust replay and C oracle.
- 通过 Rust replay 与 C oracle 验证重复 timestamp 和倒退 timestamp 的 append 失败。
- Prove both failed appends report `status:"error"` and `code:"FDB_WRITE_ERR"`.
- 证明两个失败 append 都报告 `status:"error"` 与 `code:"FDB_WRITE_ERR"`。
- Prove failed appends do not create visible TSDB records, do not consume successful `entry_id` values, and do not corrupt later append/query/count/reopen behavior.
- 证明失败 append 不产生可见 TSDB 记录、不消耗成功记录的 `entry_id`，且不破坏后续 append/query/count/reopen 行为。
- Keep first-party non-test unsafe at 0%.
- 保持一方非测试 Rust unsafe 为 0%。

**Non-Goals:**

- Do not validate timestamp overflow, negative timestamp policy, 64-bit timestamp builds, capacity pressure, sector rollover/full, clean/GC, physical deletion, corrupt-image reopen, byte-for-byte layout, payload-size behavior, async/threading, or power-loss behavior.
- 不验证 timestamp 溢出、负 timestamp 策略、64-bit timestamp 构建、容量压力、sector rollover/full、clean/GC、物理删除、损坏镜像 reopen、字节级布局、payload-size 行为、异步/多线程或断电行为。
- Do not change the replay fixture schema unless existing operations cannot express the behavior.
- 除非现有 operation 无法表达该行为，否则不修改 replay fixture schema。

## Decisions

1. Use one dedicated `l3-tsdb-non-monotonic-timestamp.json` fixture.

   This keeps timestamp ordering separate from payload and status-transition slices, and lets the evidence show both `== last_time` and `< last_time` rejection in the same C rule.

   使用独立 `l3-tsdb-non-monotonic-timestamp.json` fixture。这样可以把 timestamp 顺序与 payload、状态迁移切片分开，并让证据在同一条 C 规则下展示 `== last_time` 与 `< last_time` 两种拒绝。

2. Treat `cur_time <= last_time` as the strict behavior boundary.

   The C code checks less-than-or-equal, not only decreasing timestamps. The Rust patch should compare against the last successful append timestamp before allocating or persisting a new entry.

   将 `cur_time <= last_time` 作为严格行为边界。C 代码检查的是小于或等于，而不仅是倒退 timestamp。Rust 补丁应在分配或持久化新 entry 之前，与上一次成功 append 的 timestamp 对比。

3. Keep strict behavior fields broad for this slice.

   Step status, step code, operation id/name, successful `entry_id`, timestamp, query entries, counts, and error semantics are behavior. Only layout/toolchain/source metadata and free-form diagnostic messages can remain accepted differences.

   本切片保持较宽的严格行为字段。step status、step code、operation id/name、成功 `entry_id`、timestamp、query entries、counts 与 error semantics 都是行为字段；只有 layout/toolchain/source metadata 和自由诊断 message 可以作为 accepted differences。

4. Use a negative diff that mutates rejection semantics or visibility.

   The strongest small mutation is changing the duplicate or decreasing append from `error/FDB_WRITE_ERR` to `ok/OK`, or making a rejected value appear in query entries. Either must fail schema-aware diff.

   negative diff 使用拒绝语义或可见性篡改。最小且强的篡改是把重复或倒退 append 从 `error/FDB_WRITE_ERR` 改为 `ok/OK`，或让被拒绝 value 出现在 query entries 中；两者都必须被 schema-aware diff 拦截。

## Risks / Trade-offs

- Existing Rust replay accepts duplicate/decreasing timestamps -> add the focused red test first, then patch only `TsDb::append`.
- 当前 Rust replay 接受重复/倒退 timestamp -> 先增加聚焦红测，然后只补 `TsDb::append`。
- C oracle may already serialize failed append steps but message text can differ from Rust -> keep message text accepted, while status/code/visibility remain strict.
- C oracle 可能已经序列化失败 append step，但 message 文本会与 Rust 不同 -> 允许 message 文本差异，同时保持 status/code/visibility 严格。
- This slice intentionally leaves KVDB missing-delete and timestamp integer-width boundaries for later -> record them as next candidates instead of expanding the current patch.
- 本切片有意把 KVDB missing-delete 与 timestamp 整数宽度边界留到后续 -> 将它们记录为下一候选，而不是扩展当前补丁。
