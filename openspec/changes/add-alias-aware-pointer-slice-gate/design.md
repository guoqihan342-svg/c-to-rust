## Context

当前自动翻译管线已经有 `context-pack -> type-map -> CFG -> pointer-graph -> Rust draft -> rust-check -> oracle/replay/diff -> manifest` 的 L3 证据链。现有 pointer graph 可以记录 pointer nodes、dependency edges、read/write effects、boundary decisions 和 known gaps；`copy_i32_ptr_arith` 也已经证明 `*(values + i)` 输入读取与 `*(out + i)` 输出写入能进入 safe Rust replay。

缺口在 alias 语义：`values` 与 `out` 可能重叠时，C 的读写顺序和 Rust safe API 的别名约束不是同一个问题。当前系统用 `No proof for aliasing or overlap` 作为 non-goal，但这不是机器可验证 gate。下一阶段必须把 alias 风险结构化，否则进入 `memmove`、parser buffer、struct pointer、inout 参数等真实项目 slice 时，会误把“fixture 通过”解释成“alias-safe 翻译”。

## Goals / Non-Goals

**Goals:**

- 为 pointer graph 增加结构化 alias evidence：`alias_sets`、`alias_risks`、`alias_contract`、`safe_boundary_preconditions`。
- 当 slice 同时存在 pointer read 和 pointer write 时，明确区分 `proven_noalias`、`overlap_allowed`、`unknown_alias`、`alias_sensitive_blocked`。
- 把 alias gate 结果写入 translation plan、summary/final verification 和 L3 manifest，进入短全回归。
- 新增一个最小 alias-sensitive demo slice，证明系统能识别并记录 input/output 重叠风险，并通过 C oracle/Rust replay/diff 约束行为边界。
- 保持默认 safe Rust 和 first-party non-test unsafe 为 0；不得为了绕过 borrow checker 直接引入未审计 unsafe。

**Non-Goals:**

- 不证明 whole-program alias safety。
- 不实现通用 Rust borrow/ownership 推断。
- 不支持任意 `memmove`/`memcpy`/overlap buffer 自动安全翻译。
- 不把 C 的 UB、NULL pointer、负长度、signed overflow 语义纳入本变更。
- 不要求在线 AI；AI 仍只能生成候选或修复建议，不能作为正确性证据。

## Decisions

1. Alias gate 先做 evidence/gating，不先扩大 translator 语法面。
   直接扩展更多 pointer 语法会把风险埋进代码生成。本阶段先让 auto_migrate 和 evidence 明确判断“可 safe 接受、需 noalias 前置条件、或必须阻断”，再选择后续 slice。

2. Pointer graph 使用保守 alias 状态。
   默认状态是 `unknown_alias`，只有 slice spec、fixture contract 或源语义明确证明不重叠时才允许 `proven_noalias`。如果 C 语义允许 overlap，而 Rust API 使用 `&[T]` + `&mut [T]` 不能表达该语义，自动翻译必须降级为 candidate 或需要 reviewed exception。

3. Demo slice 选择 `add_i32_pair_ptr_arith`。
   形态为 `int add_i32_pair_ptr_arith(const int* lhs, const int* rhs, int len, int* out)`。`lhs/rhs` 是 read/read，可以 alias；`out` 是 write，必须与两个 input buffer disjoint。它比 `copy_i32_ptr_arith` 多一个输入指针和 alias matrix，但仍在当前 bounded pointer arithmetic read/write 能力附近，适合作为第一版 alias gate。

4. Gate 输出必须进入 manifest。
   `alias_risks` 只存在 pointer graph 里不够；translation plan、final verification 和 manifest 都要引用 gate 状态，短全回归才能发现未来退化。

5. 失败优先于假成功。
   如果 alias 风险字段缺失、风险为 `unknown_alias` 却声明 semantic accepted、或 safe boundary 缺少 noalias precondition，validator 必须失败。

## Risks / Trade-offs

- [Risk] 过度保守导致很多真实 slice 被阻断。Mitigation: 允许 `accepted_evidence_bound` 和 reviewed exception，但必须在 evidence 中记录边界、非目标和后续工作。
- [Risk] demo slice 太人工，不能代表真实项目。Mitigation: 先落门禁和证据形态，再用 libuv/nginx/parser 类 slice 扩展。
- [Risk] alias 字段与 pointer graph 现有字段重复。Mitigation: 保留现有 `dependency_edges`，新增字段只表达别名关系和接收策略。
- [Risk] safe Rust wrapper 改变 C overlap 语义。Mitigation: 对 noalias wrapper 明确记录 `requires_noalias_contract:true`，对 overlap 语义不自动声明 accepted safe translation。
- [Risk] validators 只检查字段存在。Mitigation: tests 必须覆盖正向 noalias、unknown alias 阻断、manifest 缺字段失败和 negative diff。

## Migration Plan

1. 编写 auto_migrate 红测：alias-sensitive slice 应产生 `alias_risks`，unknown alias 不能 false success。
2. 扩展 pointer graph normalization 和 manifest/plan 输出。
3. 新增 alias demo slice 的 C oracle generator、Rust replay、fixture、L3 evidence tests。
4. 接入 full-regression smoke。
5. 跑 targeted tests、OpenSpec strict/all、短全回归后再提交。

Rollback：如果 alias gate 误伤现有 slice，可只关闭新 validator 对旧 evidence 的强制要求，保留新 demo 和 spec；不得删除已有 pointer graph evidence。
