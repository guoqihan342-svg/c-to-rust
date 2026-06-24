## Context

FlashDB Rust already supports TSDB append, query, set-status, count-by-status, reopen, and error reporting through replay step `status` and `code`. Existing TSDB L3 slices validate append/query/status main paths and deleted-status persistence, but they do not independently validate public TSDB error-boundary behavior. The C oracle also reports stable TSDB errors for unknown `entry_id`, unknown status strings, invalid numeric fields, and missing required fields.

FlashDB Rust 当前已经支持 TSDB append、query、set-status、count-by-status、reopen，并通过 replay step 的 `status` 与 `code` 报告错误。现有 TSDB L3 切片验证了 append/query/status 主路径和 deleted 状态持久化，但还没有单独验证公开可见的 TSDB 错误边界行为。C oracle 也能对未知 `entry_id`、未知状态字符串、非法数字字段和缺失必填字段输出稳定 TSDB 错误。

## Goals / Non-Goals

**Goals:**

- Freeze one named slice: `tsdb-error-boundary`.
- Validate unknown `entry_id` for `ts.set_status`, unknown TS status for `ts.set_status` and `ts.count_status`, invalid timestamp for `ts.append`, missing range field for `ts.query`, and valid TSDB behavior after those errors.
- Generate Rust replay and WSL/Linux/CI C oracle reports from the same fixture and compare them with schema-aware diff.
- Add negative diff coverage proving step `status`, step `code`, operation id, operation name, operation success, `entry_id`, `timestamp`, `value`, `count`, and `entries` cannot be hidden by accepted differences.
- Keep first-party non-test unsafe at 0% for this slice.
- Reuse the established compile self-healing, cache, unsafe, performance, and summary evidence formats.

**目标：**

- 固化一个命名切片：`tsdb-error-boundary`。
- 验证 `ts.set_status` 未知 `entry_id`、`ts.set_status` 与 `ts.count_status` 的未知 TS 状态、`ts.append` 非法 timestamp、`ts.query` 缺失范围字段，以及这些错误之后 TSDB 仍可继续执行有效行为。
- 使用同一 fixture 生成 Rust replay 与 WSL/Linux/CI C oracle 报告，并通过 schema-aware diff 对比。
- 增加负向 diff 覆盖，证明 step `status`、step `code`、操作 id、操作名、操作成功状态、`entry_id`、`timestamp`、`value`、`count` 与 `entries` 不能被 accepted differences 掩盖。
- 本切片保持一方非测试代码 unsafe 为 0%。
- 复用现有编译自愈、缓存、unsafe、性能烟测和总结证据格式。

**Non-Goals:**

- Do not claim TSDB capacity exhaustion, sector full, layout, byte-for-byte image equivalence, power-loss, corrupt-image reopen, clean, GC, or physical deletion behavior.
- Do not claim payload maximum length or arbitrary binary payload behavior; the replay fixture DSL uses string fields.
- Do not treat `ts.query` with `from > to` as an error; that is normal reverse query behavior covered by the existing TSDB main-path slice.
- Do not use exact diagnostic `message` text as a correctness gate; strict gates use machine-checkable `status`, `code`, step identity, and behavior fields.
- Do not add async runtime, internal multithreading, or concurrency behavior.
- Do not broaden accepted differences to include behavior fields.

**非目标：**

- 不声明 TSDB 容量耗尽、sector full、布局、字节级镜像等价、掉电、损坏镜像 reopen、clean、GC 或物理删除行为。
- 不声明 payload 最大长度或任意二进制 payload 行为；replay fixture DSL 使用字符串字段。
- 不把 `ts.query` 的 `from > to` 当成错误；它是已有 TSDB 主路径切片覆盖的正常反向查询行为。
- 不把精确诊断 `message` 文本作为正确性门禁；严格门禁使用可机器检查的 `status`、`code`、step identity 和行为字段。
- 不引入 async runtime、内部多线程或并发语义。
- 不把行为字段加入 accepted differences。

## Decisions

1. **Use replay-visible TSDB input errors as the slice boundary.**
   The fixture covers stable C/Rust comparable errors: unknown `entry_id`, unknown TS status, invalid timestamp, and missing required query field. It also includes successful operations after errors to prove the replay loop and TSDB state remain usable.

   **使用 replay 可见的 TSDB 输入错误作为切片边界。**
   fixture 覆盖 C/Rust 可稳定对比的错误：未知 `entry_id`、未知 TS 状态、非法 timestamp 和缺失必填 query 字段。它也包含错误后的成功操作，用于证明 replay 循环与 TSDB 状态仍可继续使用。

2. **Allow diagnostic `message` differences, but not `status` or `code`.**
   Rust messages include typed error prefixes such as `parse error:` and `invalid range:`, while C oracle messages are shorter. Accepted differences may include `message`, but `status`, `code`, operation identity, and behavior fields must remain strict.

   **允许诊断 `message` 差异，但不允许 `status` 或 `code` 差异。**
   Rust message 会包含 `parse error:`、`invalid range:` 等类型前缀，而 C oracle message 更短。accepted differences 可以包含 `message`，但 `status`、`code`、操作身份和行为字段必须保持严格。

3. **Do not rely on successful `ts.set_status` output in this slice.**
   Earlier evidence records that successful `ts.set_status` reports currently use duplicate `status` JSON keys. This slice only uses `ts.set_status` error paths, avoiding claims about schema-level separation of step status and entry status.

   **本切片不依赖成功 `ts.set_status` 输出。**
   既有证据记录了成功 `ts.set_status` 报告当前存在重复 `status` JSON key。本切片只使用 `ts.set_status` 错误路径，避免声明 step status 与 entry status 已在 schema 层分离。

4. **Do not change production API unless validation exposes a parity gap.**
   Current Rust and C oracle code already supports the operations required by this slice. Any production change must be driven by a failing test or diff, and must stay inside the TSDB impact set.

   **除非验证暴露等价性缺口，否则不修改生产 API。**
   当前 Rust 与 C oracle 已支持本切片需要的操作。任何生产代码修改都必须由失败测试或 diff 驱动，并且限制在 TSDB 影响集内。

5. **Use bounded parallelism.**
   Parallel agents may review Rust error boundaries, C oracle boundaries, evidence completeness, and patch risk. Code edits remain single-writer to avoid conflicting patches.

   **使用有边界的并行。**
   多智能体可以审查 Rust 错误边界、C oracle 边界、证据完整性和补丁风险；代码编辑仍由单写者串行完成，避免补丁冲突。

## Risks / Trade-offs

- **Message strings differ between C and Rust** -> Treat `message` as accepted diagnostic metadata; require strict `status` and `code` parity.
- **Fixture could drift into layout or capacity behavior** -> Explicitly exclude capacity, payload limits, corrupt image, clean, GC, and sector-full behavior.
- **Diff allowlist could hide error semantics** -> Add a negative diff mutating `code` or `status`, and forbid behavior fields in accepted differences.
- **Successful `ts.set_status` schema remains ambiguous** -> Avoid depending on successful `ts.set_status` fields and record the known gap in summary.
- **Automatic repair could widen scope** -> Patch evidence must block unsafe, public API changes outside impact set, C oracle contract changes, fixture behavior changes, or accepted-difference widening.
