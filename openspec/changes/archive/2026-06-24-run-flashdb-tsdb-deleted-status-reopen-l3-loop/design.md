## Context

FlashDB Rust already supports TSDB append, query, set-status, count-by-status, and reopen behavior. The replay layer parses `deleted` and `user2`, and the C oracle maps `deleted` to `FDB_TSL_DELETED`. The existing `tsdb-append-query-status` L3 slice validates `written` and `user1`, but it does not independently validate `deleted` status persistence through reopen.

FlashDB Rust 当前已经支持 TSDB append、query、set-status、count-by-status 和 reopen。replay 层可以解析 `deleted` 与 `user2`，C oracle 也会把 `deleted` 映射到 `FDB_TSL_DELETED`。现有 `tsdb-append-query-status` L3 切片验证了 `written` 与 `user1`，但还没有单独验证 `deleted` 状态经过 reopen 后仍然持久化。

## Goals / Non-Goals

**Goals:**

- Freeze one named slice: `tsdb-deleted-status-reopen`.
- Validate two TSDB appends, setting entry 1 to `deleted`, counting `deleted`, counting remaining `written`, reopening, and recounting `deleted`.
- Generate Rust replay and WSL/Linux/CI C oracle reports from the same fixture and compare them with schema-aware diff.
- Add negative diff coverage proving `count`, `status`, `entry_id`, operation id, operation name, step `status`, and step `code` cannot be hidden by accepted differences.
- Keep first-party non-test unsafe at 0% for this slice.
- Reuse the established compile self-healing, cache, unsafe, performance, and summary evidence formats.

**目标：**

- 固化一个命名切片：`tsdb-deleted-status-reopen`。
- 验证两次 TSDB append、将 entry 1 设置为 `deleted`、统计 `deleted`、统计剩余 `written`、reopen、以及 reopen 后再次统计 `deleted`。
- 使用同一 fixture 生成 Rust replay 与 WSL/Linux/CI C oracle 报告，并通过 schema-aware diff 对比。
- 增加负向 diff 覆盖，证明 `count`、`status`、`entry_id`、操作 id、操作名、step `status`、step `code` 不能被 accepted differences 掩盖。
- 本切片保持一方非测试代码 unsafe 为 0%。
- 复用现有编译自愈、缓存、unsafe、性能烟测和总结证据格式。

**Non-Goals:**

- Do not claim `fdb_tsl_clean` or physical deletion behavior.
- Do not claim deleted entries are included or excluded from `ts.query` results; this slice uses `count_status` as the public behavior gate.
- Do not claim byte-for-byte flash image layout equivalence, sector rollover/full behavior, power-loss recovery, or capacity-pressure behavior.
- Do not cover non-monotonic timestamp rejection, max payload length, `user2`, or TSDB error-boundary cases.
- Do not add async runtime, internal multithreading, or concurrency behavior.
- Do not broaden accepted differences to include behavior fields.

**非目标：**

- 不声明 `fdb_tsl_clean` 或物理删除行为。
- 不声明 deleted 记录是否会出现在 `ts.query` 结果中；本切片只用 `count_status` 作为公开行为门禁。
- 不声明 flash 镜像字节级布局等价、扇区滚转/full、掉电恢复或容量压力行为。
- 不覆盖非单调时间戳拒绝、最大 payload、`user2` 或 TSDB 错误边界。
- 不引入 async runtime、内部多线程或并发语义。
- 不把行为字段加入 accepted differences。

## Decisions

1. **Use `count_status` instead of `query` for deleted behavior.**
   The fixture checks `deleted` and `written` counts before and after reopen. This avoids overclaiming how native FlashDB iterators expose deleted records while still validating the public status-count semantics both implementations support.

   **使用 `count_status` 而不是 `query` 验证 deleted 行为。**
   fixture 检查 reopen 前后的 `deleted` 与 `written` 计数，避免过度声明原生 FlashDB iterator 如何暴露 deleted 记录，同时仍验证双方都支持的公开状态计数语义。

2. **Use a new L3 fixture instead of extending `l3-tsdb-append-query-status.json`.**
   `flashDB_rust/fixtures/l3-tsdb-deleted-status-reopen.json` makes this evidence boundary explicit and keeps the earlier TSDB slice stable.

   **使用新的 L3 fixture，而不是扩展既有 fixture。**
   `flashDB_rust/fixtures/l3-tsdb-deleted-status-reopen.json` 明确了本次证据边界，并保持已有 TSDB 切片稳定。

3. **Keep behavior fields non-ignorable.**
   Accepted differences may include metadata such as `image_hash`, `backend`, `toolchain_status`, `source`, `fixture`, `fixture_hash`, and `report_path`. They must not include `entry_id`, `timestamp`, `status`, `value`, `count`, step `status`, step `code`, operation id, operation name, or operation success.

   **行为字段不可忽略。**
   accepted differences 只能包含 `image_hash`、`backend`、`toolchain_status`、`source`、`fixture`、`fixture_hash`、`report_path` 等元数据，不能包含 `entry_id`、`timestamp`、`status`、`value`、`count`、step `status`、step `code`、操作 id、操作名或操作成功状态。

4. **Do not change production API unless validation exposes a parity gap.**
   Current Rust and C oracle code already supports the operations required by this slice. Any production change must be driven by a failing test or diff, and must stay inside the TSDB impact set.

   **除非验证暴露等价性缺口，否则不修改生产 API。**
   当前 Rust 与 C oracle 已支持本切片需要的操作。任何生产代码修改都必须由失败测试或 diff 驱动，并且限制在 TSDB 影响集内。

5. **Use bounded parallelism.**
   Parallel agents may review fixture scope, C oracle boundaries, and evidence completeness. Code edits remain single-writer to avoid conflicting patches.

   **使用有边界的并行。**
   多智能体可以审查 fixture 范围、C oracle 边界和证据完整性；代码编辑仍由单写者串行完成，避免补丁冲突。

## Risks / Trade-offs

- **Deleted query semantics may differ** -> Avoid query assertions for deleted records in this slice; use count-status gates only.
- **Entry id mapping may drift** -> The fixture uses deterministic append order and diff treats `entry_id` as behavior.
- **Diff allowlist could hide status drift** -> Add a negative diff that mutates the deleted count or status field and requires failure.
- **C oracle invalid status or clean behavior is out of scope** -> Record these as later slices instead of expanding this loop.
- **Automatic repair could widen scope** -> Patch evidence must block unsafe, public API changes outside impact set, C oracle contract changes, fixture behavior changes, or accepted-difference widening.

中文说明：主要风险是 deleted 查询语义、entry id 漂移、diff 白名单过宽和自愈补丁越界。本设计通过只验证 count-status、固定 append 顺序、负向 diff、以及补丁证据门禁来降低风险。
