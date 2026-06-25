## Context

`crates/c2r-translator` 当前已经能处理普通 assignment、compound assignment、inc/dec、结构化 if/while/for，以及一条 pointer field safe-wrapper 路径。现状问题是 lvalue 判断分散在字符串检查中：`addr->field = value` 会被归为 `PointerWrite`，但 `arr[i] = value`、`s.field = value` 可能被普通 assignment 放行；`arr[i] += value` 又因为 compound assignment 只接受 simple identifier 被 block。下一步不能直接扩大 Rust emission，而要先让 lvalue 形态变成显式决策。

该 change 的目标是把 pointer graph 从“记录发生了什么”提升为“控制是否允许生成候选 draft”的 gate。它仍然只是 bounded translator 的小步，不声称解决 C 指针完整语义。

## Goals / Non-Goals

**Goals:**
- 增加小型 lvalue classifier，覆盖 simple identifier、pointer field、dereference identifier、常量零 pointer index、unsupported complex lvalue。
- 防止 `arr[i] = value`、`s.field = value`、`*(out + i) = value` 被普通 assignment 误翻译。
- 对受限 pointer-out 写入生成 pointer graph decision、translation rule id 和 normalized evidence。
- 保持 pointer-bearing public API 的 safe wrapper/report boundary。
- 增加 translator tests、auto_migrate tests、OpenSpec validation 和短回归 smoke。

**Non-Goals:**
- 不做任意 C 指针别名分析。
- 不推断 struct layout、数组长度、宏展开字段偏移或 volatile 语义。
- 不把 raw pointer 暴露为默认 Rust public API。
- 不承诺 `out[i]` 这类变量索引安全，除非当前 slice 能明确证明边界。
- 不引入新的 unsafe Rust 作为默认实现策略。

## Decisions

1. 使用小型 `LValue` 分类，而不是在 `translate_expr()` 里继续字符串透传。
   Rationale: 当前 false-success 风险来自 assignment 过早放行。把 lvalue 作为分类结果可以在 emit 前 block，且能写入 CFG/pointer evidence。
   Alternative considered: 只在 `parse_assignment()` 加更多字符串禁止项。Rejected because it would keep decision logic fragmented and hard to audit.

2. 先支持 `out[0]`，暂不支持未证明的 `out[i]`。
   Rationale: `out[0]` 是常见 out-param single-slot pattern，可以作为 pointer index MVP；变量索引需要循环条件、长度参数和 alias 分析，容易过度承诺。
   Alternative considered: 支持任意 `out[i]` 并交给 replay 测试兜底。Rejected because replay cannot prove memory safety or bounds in untested paths.

3. pointer-bearing 函数继续走 safe wrapper/report boundary。
   Rationale: 用户要求 unsafe 比例受控，现有 pipeline 也要求 public API 默认安全。该 change 只扩大 translator 对 C 写入模式的识别和 evidence，不改变 public raw pointer 策略。
   Alternative considered: 生成 internal raw pointer helper. Rejected for this MVP because it would require new unsafe ledger and stronger alias evidence.

4. normalized evidence 保留 translator 决策，而不是只检查 Rust draft 文本。
   Rationale: 后续 agent/CI 需要能从 `cfg.json`、`pointer-graph.json` 和 `auto-translation-plan.json` 追踪为什么某个 lvalue 被接受或拒绝。

## Risks / Trade-offs

- [Risk] 过宽 lvalue classifier 可能把复杂 C 语义误判为安全。→ Mitigation: 白名单分类，负向测试覆盖 `s.field`、`arr[i]`、`*(out+i)`。
- [Risk] 只支持 `out[0]` 覆盖面有限。→ Mitigation: 这是有意的小步；变量索引留给后续“loop bound proof” change。
- [Risk] safe wrapper draft 可能编译通过但没有语义等价。→ Mitigation: auto_migrate manifest 继续保持 `semantic_pass=false`，必须走 C oracle/replay/diff。
- [Risk] normalized evidence 新字段影响旧验证。→ Mitigation: 只添加兼容字段，不删除现有字段；验证用 OpenSpec 和 auto_migrate 单测兜底。

## Migration Plan

1. 先新增红灯 tests：正向 pointer field 多写入、正向 `out[0]`、负向 `arr[i]`、负向 `s.field`、负向 `*(out+i)`。
2. 实现 lvalue classifier 和 pointer graph decision emission。
3. 更新 auto_migrate normalizer，保留 lvalue kinds / pointer decisions / rule ids。
4. 跑 translator tests、auto_migrate tests、OpenSpec validation、short full-regression smoke。
5. 若实现发现需要更强的边界证明，保持 block 行为并在 tasks/spec 中记录为后续 change。

## Open Questions

- `out[0] += value` 是否应在本 change 直接生成 safe wrapper candidate，还是先只记录 pointer graph decision 并 block semantic acceptance。默认选择：生成 candidate，但保持 semantic pass false。
- `int* out` 的 public report 类型是否需要专门命名，还是沿用现有 pointer safe-wrapper report。默认选择：沿用现有 report pattern，避免扩大 public API。
