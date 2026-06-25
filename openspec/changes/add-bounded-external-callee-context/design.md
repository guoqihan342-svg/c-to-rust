## Context

`add-call-expression-l3-demo-slice` 已证明 bounded direct call expression 能进入 translation plan、context pack、C oracle/Rust replay、diff、negative diff、unsafe 和 auto evidence manifest。但该 demo 使用 self-recursive callee，避开了真实 C slice 中常见的外部 helper 函数。

当前 translator 已能识别 `helper(value)` 这类 direct identifier call，并把 callee、arguments、source expression、statement context 写入 `plan.call_expressions`。缺口发生在 `auto_migrate` 的 standalone rust-check：translator 生成的 Rust draft 会保留 `helper(...)`，但 draft 文件没有 `fn helper`，因此 rustc 会报 unresolved function。

## Goals / Non-Goals

**Goals:**
- 支持 spec 显式声明的一层 external direct callee context。
- 让 `auto_migrate` 为 declared helper callee 生成 compile-only Rust stub，使 generated draft 可以 standalone rust-check。
- 在 normalized plan、context pack、manifest、final verification 中记录 external callee 的来源、stub kind、semantic boundary 和 blocking reason。
- 新增 L3 demo slice 验证 external helper direct call evidence 不丢失，并保持 accepted semantics 仍由 C oracle/Rust replay/diff/negative diff 证明。

**Non-Goals:**
- 不做任意多函数 C 翻译器。
- 不声明 compile-only stub 具备 helper 语义。
- 不支持函数指针、成员调用、宏调用、nested call、variadic call、多层调用图、互递归、状态ful helper、指针/struct helper 参数。
- 不扩大 unsafe 预算；first-party non-test unsafe 仍应保持 0。

## Decisions

1. 在 `auto_migrate` 注入 compile-only helper stub，而不是在 translator 做多函数翻译。
   - 理由：translator 已完成 call expression 识别和 Rust call 生成；当前失败点是 standalone draft 的编译上下文。
   - 替代方案：translator 接收多个 C function 并生成多函数 Rust。该方案更完整，但会牵涉函数顺序、重复符号、跨文件 hash、多层语义 claim，范围过大。

2. helper 必须由 slice spec 显式声明。
   - `c_boundary.signatures[]` 可包含 primary function 之外的 helper signature 和 bounded `c_source`。
   - `c_boundary.direct_dependencies[]` 记录 `kind: "callee"`、`name`、`source`、可选 `semantic_role`。
   - 未声明 helper 不自动注入 stub，必须产生 blocked evidence 或 rust-check failure。

3. stub 是 compile-only，不是 semantic evidence。
   - Rust draft 前置形如 `fn helper_add_one(value: i32) -> i32 { unimplemented!("external callee context stub: helper_add_one") }`。
   - context pack 和 manifest 记录 `stub_kind: "compile_only"`、`semantics_verified: false`。
   - accepted semantic pass 仍只能来自 direct L3 evidence 的 C oracle、Rust replay、schema diff、negative diff、unsafe 和 final verification。

4. 首批只支持 primitive integer helper signature。
   - 支持 `int helper(int value)` 映射到 `fn helper(value: i32) -> i32`。
   - 参数名和 callee 名必须走 Rust identifier sanitization，避免 keyword 触发无意义 rust-check failure。
   - 其他类型先 blocked，并写入 unsupported callee reason。

## Risks / Trade-offs

- [Risk] rust-check 通过后被误读为 generated draft 语义通过。→ Mitigation: 所有 evidence 写明 compile-only stub，`generated_draft_semantic_pass` 保持 false，final semantic pass 绑定 accepted evidence。
- [Risk] helper declaration 与实际 C helper 语义不一致。→ Mitigation: spec 需要 helper signature/source hash，L3 demo 用 C oracle/Rust replay 证明 observable output，而不是信任 stub。
- [Risk] 自动 stub 掩盖 missing context。→ Mitigation: 只有 spec 显式声明且 call_expressions 引用的 callee 可注入；未声明 callee 必须 fail/blocked。
- [Risk] 支持面扩张过快。→ Mitigation: 本 change 限定一层 primitive direct callee；跨文件真实源码抽取、函数体翻译、多层 call graph 单独后续 change。
