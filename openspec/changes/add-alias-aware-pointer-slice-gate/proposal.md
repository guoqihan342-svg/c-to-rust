## Why

当前自动翻译管线已经能处理受限的输入 buffer 读取和输出 buffer 写入，但 `values` 与 `out` 是否可能 alias 仍主要停留在 `non_goals` 文本里。进入更复杂 C 项目后，这会让 Agent 在没有明确风险门禁的情况下把含读写指针的 slice 包装成 safe Rust，从而高估语义等价性。

本变更把 alias 风险提升为机器可读、可验证、可阻断的 pointer slice gate：当 slice 同时存在指针读写、多个可变指针、输入输出 buffer 可能重叠、或 struct/raw pointer 依赖链时，系统必须记录 alias class、风险等级、证据来源和最终策略，不能只用自然语言说明风险。

## What Changes

- 在 bounded auto-translation pipeline 中增加 alias-aware pointer slice gate，要求 pointer graph 输出结构化 alias 风险字段。
- 对含读写指针的 slice 生成 `alias_sets`、`alias_risks`、`alias_contract`、`safe_boundary_preconditions` 和 `blocked_reasons`。
- 对无法证明 noalias 的 safe Rust 公共边界进行降级：只能记录候选 draft 或 accepted evidence binding，不能声明 alias-safe 自动翻译成功。
- 增加一个比纯函数和单向 buffer 更难的 demo slice，用 fixture 覆盖 input/output 分离与重叠风险，并通过 L3 evidence 证明“风险被记录和门禁处理”，而不是声称完整 alias safety。
- 保持 unsafe 预算约束：默认仍不新增 first-party unsafe；如果后续需要内部 unsafe，必须走 unsafe ledger 和 10% 以下预算。

## Capabilities

### New Capabilities
- `alias-aware-pointer-l3-demo-slice`: 用一个小型但 alias-sensitive 的 C slice 验证 alias 风险门禁、C oracle/Rust replay/diff/negative diff 和 unsafe scan。

### Modified Capabilities
- `bounded-auto-translation-pipeline`: 指针图不再只记录 pointer nodes/edges；当存在 alias-sensitive 读写组合时，必须记录结构化 alias gate 输出，并把它纳入 translation plan、manifest 和 final verification。

## Impact

- `validation/tools/auto_migrate.py`: 规范化 pointer graph 时增加 alias 风险字段和 acceptance 降级逻辑。
- `validation/tools/test_auto_migrate.py`: 增加 alias-sensitive slice 的红绿测试。
- `validation/slice-specs/`: 新增 alias demo slice spec。
- `validation/l2_slices/`: 新增 C oracle fixture generator、Rust replay、测试和 report emitter。
- `validation/evidence/`: 新增 alias demo 的 L3 evidence 和 auto-translation evidence。
- `scripts/run-full-regression.ps1`: 增加 alias demo semantic/risk gate 的短回归步骤。
- `openspec/specs/`: 新增 alias-aware gate 能力，并修改 bounded auto-translation pipeline 的 pointer evidence 要求。
