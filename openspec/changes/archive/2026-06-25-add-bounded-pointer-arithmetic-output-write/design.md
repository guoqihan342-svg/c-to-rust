## Context

当前 translator 的 pointer 能力已经覆盖三类受限路径：`out[0]` 标量 out-param、`values[i]` bounded input-buffer read、`*(values + i)` bounded pointer-arithmetic input read。`*(out + i) = expr` 现在会在 `parse_lvalue()` 阶段作为 complex dereference 被拒绝，并且不会被误判为 input read。

本设计把 `*(out + i)` 写入作为独立 output-buffer write 能力处理，而不是放开通用 pointer arithmetic。The safe Rust public boundary must not expose raw pointers and must preserve the evidence trail from raw C write to canonical Rust write.

## Goals / Non-Goals

**Goals:**

- 在已证明的 `for (int i = 0; i < len; i++)` bounded loop 内识别 `*(out + i) = expr`。
- 将该写法 canonicalize 为 `out[i]`，Rust draft 使用 safe mutable slice 写入 `out[i as usize] = ...;`。
- 在 pointer graph、CFG、translation plan、events 中记录 raw write、canonical write、length companion、translation rule id。
- 增加 `copy_i32_ptr_arith` L3 demo，验证实际 `out_values` 与 C oracle 等价，而不只比较 evidence 字段。
- 保持已有 scalar out-param report 路径和 bounded input read 路径不变。

**Non-Goals:**

- 不支持任意 C pointer arithmetic、`out++`、`*(out + i + 1)`、`*(out - i)`、cast、函数调用 index、side-effect index。
- 不支持没有 proven loop bound 的 `*(out + i)` 写入。
- 不支持 compound pointer arithmetic assignment，例如 `*(out + i) += value`。
- 不在本变更内证明 input/output aliasing；涉及 `const int* values` 与 `int* out` 同 loop 读写时，只有 demo/replay 能证明的安全边界才可通过。
- 不暴露 raw pointer public API，不引入 first-party unsafe。
- 不声明 NULL pointer、negative len、signed overflow、容量压力、真实项目全库迁移。

## Decisions

1. 新增 output-write 专用 lvalue，而不是扩展 input read。

   `*(out + i)` 在 LHS 上是写入能力，证明条件和 evidence 字段都不同于 RHS input read。新增专用 kind/rule 能避免把写上下文误记为 read，也能让 unsupported case 保持明确。

2. Safe Rust boundary 使用 `&mut [i32]` 表达 caller-provided output buffer。

   现有 `out[0]` 路径把标量 out-param 折成 owned report 字段；连续 output buffer 写入更接近 `&mut [i32]`。Translator 生成的 public API 必须检查 `len` 与 `out.len()`/`values.len()` 的关系，或者在 demo replay 中使用 owned `Vec` 作为等价输出报告，但 raw pointer 不进入 public API。

3. 只接受最小可证明 loop 模式。

   合法形态限定为 `for (int i = 0; i < len; i++) { *(out + i) = expr; }`，其中 `out` 是非 const `int*` 参数，`i` 是当前 loop index，`len` 是已识别 length companion。复杂 index、非同名 bound、`i <= len`、`len + 1` 等都记录 unsupported。

4. L3 demo 用实际 `out_values` 做等价核心。

   `copy_i32_ptr_arith` 的 C oracle 写入 `out` 数组，Rust replay 返回 `out_values`。schema diff 和 negative diff 必须覆盖 `out_values`，否则不能证明 output write 语义。

## Risks / Trade-offs

- [Risk] 误把无边界 pointer write 生成为 safe slice write -> Mitigation: red test 覆盖无 loop bound、错误 bound、复杂 index 和 side effect，unsupported event 必须存在。
- [Risk] safe Rust `&[i32]` + `&mut [i32]` 非别名假设改变可别名 C 语义 -> Mitigation: 本变更默认不接受未证明 alias-sensitive input/output 同 loop 读写；demo report 记录 aliasing non-goal。
- [Risk] evidence 只记录 canonical `out[i]`，丢失 C 原始形态 -> Mitigation: pointer graph/CFG/test translation 同时保留 `*(out + i)` 和 `out[i]`。
- [Risk] L3 demo 退化为手写验证模板 -> Mitigation: auto_migrate evidence 必须从 slice spec 生成 translator input、Rust draft、plan、events，并通过 semantic gate。
- [Risk] 新 `&mut [i32]` emit 影响已有 `out[0]` report 路径 -> Mitigation: 通过独立 support predicate 选择路径，现有 tests 作为回归门禁。

## Migration Plan

1. 写 translator 红测，覆盖正向 bounded output write 和负向 unsupported case。
2. 扩展 lvalue/loop proof、pointer graph、CFG、plan、Rust emit，只让红测通过。
3. 增加 `copy_i32_ptr_arith` Rust replay、C oracle fixture、slice spec、L3 evidence 生成和 validators。
4. 更新 full-regression short smoke gate 和 OpenSpec tasks。
5. 运行 targeted tests、fmt/clippy、Python validation、OpenSpec strict/all、short full-regression 后提交。

Rollback 策略：该能力是新增 rule 和新 demo slice。若发现误识别，可以禁用 `bounded-pointer-arithmetic-output-write` 支持，让相关 slice 回到 unsupported，不影响现有 input read 或 scalar out-param 路径。
