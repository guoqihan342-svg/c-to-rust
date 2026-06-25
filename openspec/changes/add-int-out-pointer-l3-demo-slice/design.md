## Context

当前仓库已经具备 L0-L3 门禁、FlashDB L3 证据模板、libuv 指针 slice、以及 `out[0]` lvalue 翻译器支持。缺口在于：`out[0]` 能力尚未跑过一条可重复的 C/Rust 等价闭环，无法证明它能作为受限自动翻译器的一部分稳定交付。

`store_add_one` 刻意保持业务逻辑很小，但它覆盖了真正的指针输出边界：C API 通过 `int* out` 写结果，Rust API 必须暴露 safe 函数并在 replay 中证明输出值和返回码与 C oracle 一致。

## Goals / Non-Goals

**Goals:**
- 用最小 slice 验证 `out[0]` 指针输出翻译能力可以进入 L3 evidence manifest。
- 生成或登记 context pack、pointer graph、type map、CFG、C oracle、Rust replay、diff、negative diff、unsafe scan 和 summary。
- 把证据链接入低成本 smoke/full-regression 步骤，确保后续变更不会绕过这条能力。
- 保持 Rust first-party unsafe usage 为 0，并在证据里显式记录。

**Non-Goals:**
- 不声明支持 `out[i]`、`*(out + i)`、aliasing、结构体字段写入或任意指针算术。
- 不把该 demo 等同于 FlashDB 全库迁移，也不声明覆盖真实业务存储状态机。
- 不引入新外部依赖或长耗时 fuzz/stress 任务。

## Decisions

1. Use a deterministic demo slice before a larger third-party pointer slice.
   - Rationale: `store_add_one` 能隔离 `out[0]` 语义，失败时根因清晰。
   - Alternative: 直接推进 nginx/libuv 复杂 slice；风险是 alias、宏、平台依赖会掩盖翻译器本身的输出指针问题。

2. Reuse existing validation layouts instead of adding a second framework.
   - Rationale: 项目已有 slice spec、l3-template、Rust replay、schema diff 和 regression 脚本，新增能力应该进入这些门禁。
   - Alternative: 写独立 demo runner；会形成旁路，不能证明主回归能守住能力。

3. Treat unsafe scan as required evidence even when the count is zero.
   - Rationale: 用户要求 unsafe 比例受控，论文反馈也指出 0 unsafe 需要系统化审计证据而不是“碰巧没有”。
   - Alternative: 只靠代码审查；不可回放，也不能进入 evidence manifest。

4. Keep the public Rust API safe and explicit.
   - Rationale: C 的 `int* out` 应翻译为 safe return/report 边界，而不是向外暴露 `*mut i32`。
   - Alternative: 生成 raw pointer Rust；能更贴近 C ABI，但违反当前受限自动翻译器目标。

## Risks / Trade-offs

- [Risk] Demo slice 过小，不能代表真实 alias 难题 -> Mitigation: 在 Non-Goals 中明确边界，并把它作为进入更复杂指针 slice 前的 gate。
- [Risk] 证据文件变多增加维护成本 -> Mitigation: 复用已有命名和验证工具，只加入低成本 deterministic case。
- [Risk] 回归脚本变慢 -> Mitigation: 只接入常规 1 轮 smoke 所需的 schema/semantic checks，不新增长跑。
- [Risk] 自动翻译和手写 replay 混淆 -> Mitigation: evidence 中区分 generated draft、safe replay wrapper、oracle output 和 diff result。
