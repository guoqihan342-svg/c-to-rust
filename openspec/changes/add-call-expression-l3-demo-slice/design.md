## Context

`add-bounded-call-expression-translation` 已让 translator 对 `return helper(x)`、`int y = helper(x)`、`y = helper(x)` 这类 bounded direct call expression 产生 `call_expression`、`bounded-call-expression` 和 callee evidence。缺口是这些证据尚未经过 L3 端到端闭环验证。

为避免外部 helper 导致 generated Rust draft 无法通过 standalone `rustc`，demo slice 使用自递归 direct call expression。这样 translator draft 可以编译，同时 C oracle 和 Rust replay 都可以在小输入域里终止并对比。

## Goals / Non-Goals

**Goals:**
- 新增 `call_expression_chain` demo slice，覆盖 declaration initializer、assignment RHS、return expression 的 direct call evidence。
- 通过 C oracle + Rust replay + schema diff + negative diff 验证 observable behavior。
- 通过 auto evidence manifest 证明 `call_expressions` 和 `direct_call_edges` 被保留。
- unsafe 保持 0 first-party non-test unsafe。

**Non-Goals:**
- 不支持函数指针、成员调用、宏调用、nested call、variadic、外部 callee 语义验证。
- 不声明递归性能、栈深度、大输入域或全程序调用图已经解决。
- 不把 Rust draft 的编译通过等同于 callee 语义等价；仍以 accepted C/Rust replay evidence 为准。

## Decisions

1. Demo function 使用递归而不是外部 helper。
   - 外部 helper 会让 standalone rust-check 失败，除非引入额外 stub 机制；递归 call expression 更小，且能覆盖同样的语法位置。

2. 输入域保持小而确定。
   - Fixture 覆盖负数、0、1、2、3 等主路径，避免递归深度和性能问题污染本变更。

3. Negative diff 同时覆盖 output 和 call evidence。
   - 除了改错返回值，还要 mutation `call_expression_count` 或 `call_expression_contexts`，证明 diff 确实看见 call-expression 主路径。

4. Auto evidence 采用 accepted evidence binding。
   - translator 生成 draft 仍是 candidate；semantic pass 来自 committed C oracle/Rust replay/diff/unsafe evidence。

## Risks / Trade-offs

- [Risk] 自递归 demo 不代表外部跨文件 callee。Mitigation: 本变更只验证 call expression evidence pipeline；外部 callee/context pack 后续单独扩展。
- [Risk] 递归 slice 行为过于简单。Mitigation: fixture 覆盖三种 call expression context，并在 evidence 中记录 path/context，而不是只看返回值。
- [Risk] 新 evidence 文件较多。Mitigation: 沿用现有 L3 template，所有产物都纳入 summary/manifest 和 validation tests。
