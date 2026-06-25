## Context

当前自动翻译管线已经覆盖一类受限 pointer slice：`const int* values` 搭配 `len`，在 `for (int i = 0; i < len; i++)` 内读取 `values[i]`，再通过 `out[0]` 返回聚合结果。该路径已经产出 pointer graph、CFG、Rust draft、C oracle、Rust replay、schema diff、negative diff、unsafe scan 和 L3 manifest。

缺口在于等价 C 写法 `*(values + i)`。它在业务 C 代码中常见，但如果直接把所有 `*` 或 `+` 指针算术放开，会越过当前 aliasing、NULL、side effect 和 pointer write 能力边界。因此本设计只把它作为 `values[i]` 的受限语法同义形处理。

## Goals / Non-Goals

**Goals:**

- 在已证明的 bounded loop 内识别 `*(base + index)` 只读输入 buffer read。
- 将该读法 canonicalize 为 `base[index]`，Rust draft 使用 safe slice 读取 `base[index as usize]`。
- 在 pointer graph、CFG、translation plan 和 events 中记录原始形态、规范化形态、length companion、翻译规则 id。
- 增加 `sum_i32_ptr_arith` L3 demo，证明该能力能走完现有 C oracle + Rust replay + diff + unsafe + OpenSpec gate。
- 保持已有 `values[i]` 和 output pointer write 行为不变。

**Non-Goals:**

- 不支持任意 C pointer arithmetic。
- 不支持 `*(out + i) = value`、`out[i] = value` 这类 pointer/array 写入扩展。
- 不证明 aliasing、NULL 可达性、negative len、signed overflow 或容量压力语义。
- 不引入 raw pointer public API。
- 不把 AI 输出作为正确性证据。
- 不承诺 FlashDB 全库迁移或任意 C99 翻译。

## Decisions

1. `*(base + index)` 作为 input-buffer read 语法同义形，而不是新 raw pointer 模型。

   现有 translator 已有 `bounded-input-buffer-read` 规则和 safe slice public boundary。复用该边界能保持 unsafe 为 0，并避免把 demo 扩展成尚未证明的 alias analysis 问题。为便于追溯，证据中同时记录原始表达式 `*(values + i)` 和 canonical 表达式 `values[i]`，并增加更具体的 rule id `bounded-pointer-arithmetic-input-read`。

2. 只接受简单 identifier base 和简单 loop variable index。

   合法形态限定为 `*(values + i)`，其中 `values` 是只读 pointer 参数，`i` 是当前 loop index，loop condition 证明 `i < len` 或 `0 <= i && i < len`。复杂表达式、cast、side effect、`values++`、`*(values + i + 1)`、`*(values + offset)` 均记录 unsupported，避免 false success。

3. 写入上下文继续走 unsupported lvalue。

   `*(out + i) = value` 不属于本变更。左值解析仍拒绝 pointer arithmetic/complex dereference，相关负向测试用于防止读写上下文混淆。

4. L3 demo 与现有 `sum_i32_buffer` 并行，而不是替换它。

   新 slice 命名为 `sum_i32_ptr_arith` / `sum-i32-ptr-arith`。它复用同一类 fixture 域，但 C oracle 源边界必须包含 `total = total + *(values + i);`。这能证明 translator 新增能力，同时保留 `values[i]` demo 作为基线。

## Risks / Trade-offs

- [Risk] 误把无边界 `*(values + i)` 识别为安全读取 -> Mitigation: red test 要求无 proven loop 时不生成 Rust draft，并记录 unsupported。
- [Risk] 误把 `*(out + i)` 写入当成 input read -> Mitigation: 左值解析不放宽，新增守卫测试。
- [Risk] evidence 只记录 canonical read，丢失 C 原始形态 -> Mitigation: pointer graph/CFG/test translation 同时保留 raw source read 和 canonical read。
- [Risk] L3 demo 变成手写验证模板而非自动翻译能力证明 -> Mitigation: auto_migrate evidence 必须从 slice spec 生成 translator input、Rust draft、replay test draft、plan、events，并由 semantic gate 校验。
- [Risk] 后续真实项目出现 `*(i + values)`、typed offset、struct field pointer 等变体 -> Mitigation: 当前全部拒绝并记录 future capability，不在本变更内扩展。

## Migration Plan

1. 写 translator 红测，覆盖正向 `*(values + i)` 和负向无边界、写入、复杂 index。
2. 扩展 bounded read 解析、canonicalization、pointer graph/CFG/plan 证据。
3. 增加 `sum_i32_ptr_arith` Rust replay、C oracle fixture、slice spec 和 L3 evidence 生成。
4. 更新 validators、full-regression gate 和 OpenSpec tasks。
5. 运行 targeted tests、cargo fmt/test/clippy、OpenSpec strict/all、short full-regression smoke 后提交。

Rollback 策略：该能力是新增 slice 和新增识别规则。若发现误识别，可以保留 L3 demo 文件但关闭 `bounded-pointer-arithmetic-input-read` 规则，让相关 slice 回到 unsupported，不影响现有 `values[i]` 路径。

## Open Questions

- 是否后续支持 `*(i + values)` 这种交换律写法？本变更先不支持。
- 是否后续把 `len` companion 从硬编码名称泛化到 slice spec/type map？本变更先沿用当前 `len` 模式。
- 是否把 pointer arithmetic read 作为独立 `StatementKind`？实现时可在不破坏现有 schema 的前提下选择最小改动。
