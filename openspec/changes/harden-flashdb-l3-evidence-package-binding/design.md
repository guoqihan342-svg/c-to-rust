## Context

FlashDB L3 evidence package 已经包含 summary、C oracle、Rust replay、schema diff、negative diff、unsafe、version/config binding、final verification 等文件。当前 validator 会检查这些文件存在，也会检查 summary 中部分状态，但对底层正向 diff 和 final verification 的内容验证不足。

这个 change 的目标是把 L3 package 从“文件齐全”推进到“关键文件内容闭环”。它不改变 FlashDB Rust 行为，也不改变 C oracle 或 diff 生成逻辑，只收紧消费这些 evidence 的 gate。

## Goals / Non-Goals

**Goals:**
- 正向 diff 报告必须可读、状态为 passed，并且没有 first mismatch。
- final verification 报告必须可读、状态为 passed，并且关键 checks 不包含失败。
- final verification 中若记录 diff status 或 C oracle toolchain status，必须与 L3 通过条件一致。
- summary 中若记录 evidence sha256，必须与实际 evidence 文件一致。
- 新增负向单测覆盖 diff failure、final verification failure、summary hash drift。

**Non-Goals:**
- 不重生成 C oracle、Rust replay、diff 或 final verification。
- 不要求所有旧 evidence 立即新增还没有记录的 hash 字段；只在 summary 已声明 sha256 时强制校验。
- 不把 performance smoke 变成主语义 gate。
- 不改变 unsafe < 10% 的既有策略。

## Decisions

1. 在 `validate_package` 已加载所有 required evidence 后，新增内容级校验 helper。
   Rationale: 当前 `loaded` 已经包含 diff、final-verification、summary 等 JSON，最小改动是在同一个 validator 内补语义断言。
   Alternative considered: 新写一个独立 validator。Rejected because full regression already consumes `validate_flashdb_l3_evidence.py`;拆分会增加 gate 编排复杂度。

2. final verification 采用兼容字段读取。
   Rationale: 真实 evidence 可能使用 `diff_status`、`c_oracle_toolchain_status`、`checks[*].status`、`checks[*].exit_code` 等不同字段。validator 应强制已记录字段的正确性，而不是要求所有历史 package 统一 schema。
   Alternative considered: 立刻强制一个全新 final verification schema。Rejected because it would turn this hardening into migration work and risk invalidating otherwise valid committed evidence.

3. summary hash 校验只对已声明的 `sha256` 字段生效。
   Rationale: hash 绑定是高价值检查，但当前旧 summary 不一定全量记录 hash。存在声明时必须可信；不存在时先不阻塞，以便后续单独 change 推进 hash 全量化。
   Alternative considered: 要求所有 evidence refs 现在必须带 hash。Rejected because it is broader than this validator hardening slice.

## Risks / Trade-offs

- [Risk] 真实 evidence 使用不同字段名导致误报。-> Mitigation: 先抽样真实 committed evidence，helper 支持常见字段，并只强制已记录字段。
- [Risk] hash 校验路径解析错误。-> Mitigation: 复用现有 `resolve_evidence_path`，测试覆盖 declared evidence path 和 hash drift。
- [Risk] validator 变严格后 full regression 更容易失败。-> Mitigation: 先跑 unit tests，再跑 existing committed evidence validator，再跑短 full regression。

## Migration Plan

1. 写红灯单测：diff failed、final verification failed、summary hash drift。
2. 在 validator 中新增 diff、final verification、hash binding helper。
3. 更新 `validation/gates.md`。
4. 跑 unit test、validator、OpenSpec、短 full regression。
