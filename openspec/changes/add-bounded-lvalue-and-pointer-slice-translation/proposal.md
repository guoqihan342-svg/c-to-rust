## Why

当前 bounded translator 已经能处理结构化控制流、普通赋值、复合赋值和语句级自增自减，但仍存在两个关键缺口：一类真实 C slice 需要写入 pointer/array/field lvalue，另一类复杂 lvalue 可能被普通 assignment 误放行并生成不可靠 Rust draft。现在需要把 pointer graph 从“事后 evidence”推进到“翻译前决策”，让受限 pointer/lvalue slice 能自动生成候选，同时把未证明的 lvalue 明确 block。

## What Changes

- 增加受限 lvalue 分类：只区分 simple identifier、pointer field write、deref identifier write、bounded pointer index write 和 unsupported complex lvalue。
- 对 `addr->field = value`、`*out = value`、受限 `out[0] = value` / `out[0] += value` 等 pointer-out slice 生成可追踪 safe-wrapper candidate 或明确 block reason。
- 对未证明边界的 `arr[i] = value`、非 pointer-out 的 `s.field = value`、`*(out + i) = value` 等复杂 lvalue 停止生成 Rust draft，避免 false success。
- 让 pointer graph / CFG / auto-translation-plan 记录 lvalue decision、pointer boundary decision、translation rule id 和 unsupported reason。
- 增加 translator 与 auto_migrate 测试，验证正向受限 pointer write、负向复杂 lvalue、normalized evidence 和短回归 smoke。
- 不引入任意 C99 指针别名分析、struct layout 推断、数组越界证明或新 unsafe Rust API。

## Capabilities

### New Capabilities
- `bounded-lvalue-pointer-translation`: 约束 bounded translator 如何识别、翻译或拒绝 pointer/lvalue 写入，并将 pointer graph 决策绑定到自动翻译 evidence。

### Modified Capabilities
- `bounded-auto-translation-pipeline`: 扩展 pointer graph gate 和 Rust draft generation 的要求，使 pointer/lvalue decision 成为生成候选前的显式 evidence。

## Impact

- Affected crate: `crates/c2r-translator`.
- Affected tests: `crates/c2r-translator/tests/bounded_translation.rs`.
- Affected validation: `validation/tools/auto_migrate.py`, `validation/tools/test_auto_migrate.py`, and short full-regression smoke.
- Affected OpenSpec: new change artifacts plus a delta against `bounded-auto-translation-pipeline`.
- No new third-party dependencies.
