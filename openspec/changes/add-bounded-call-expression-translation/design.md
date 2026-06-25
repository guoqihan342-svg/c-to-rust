## Context

当前 `crates/c2r-translator` 已有 `StatementKind::SimpleCall`，可以把 `observe(value);` 作为 statement 记录，并输出 `simple-call` 规则。但调用出现在表达式位置时，`translate_expr` 基本只是原样保留文本。这样生成的 Rust 可能可编译，但 evidence 不知道存在 direct callee，也无法为跨文件 context pack、调用图和后续单点渐进重构建立稳定入口。

本变更把 call expression 提升为 bounded translator core 的一等结构化能力。它仍然是受限能力：只接受普通标识符 callee 和已支持的参数表达式；不解析函数体、不做内联、不推断外部库语义。

## Goals / Non-Goals

**Goals:**
- 识别 expression 位置的 direct call：return expression、declaration initializer、assignment RHS。
- 将 call expression 记录进 CFG statement kinds 和 translation rule ids。
- 为后续跨文件上下文管理保留 callee 名称、source expression 和参数列表。
- 对 side-effect 参数和非 direct identifier callee 保持阻断，避免 false success。

**Non-Goals:**
- 不支持函数指针调用、成员访问调用、宏调用还原、variadic 参数语义、跨文件函数体内联。
- 不声明 callee 本身已被 Rust 化或语义等价。
- 不为 call expression 引入 unsafe 或 raw pointer public API。
- 不扩大 signed overflow、NULL、UB、alias proof 的语义边界。

## Decisions

1. 先做 evidence-aware 的 direct call expression，而不是通用调用图。
   - 理由：当前 translator 的 parser 是 bounded extractor，不是完整 C AST。先覆盖 `helper(x)` 这种可稳定识别的表达式，可以让 context pack 和 plan 开始追踪 callee，同时避免误解复杂 C 调用语义。

2. 对调用参数复用已有 bounded expression 安全边界。
   - 允许普通标识符、整数常量、已支持的简单算术和已有 bounded buffer read canonicalization。
   - 拒绝 `i++`、`++i`、函数指针、`obj->fn(x)`、`(*fp)(x)`、嵌套调用等暂未证明形态。

3. Call expression evidence 放入 translator 输出的现有结构。
   - CFG statement kinds 追加 `call_expression`。
   - plan 追加 `bounded-call-expression`。
   - 后续如需要更细粒度调用图，可再扩展 dedicated `call_graph` evidence；本次不新增复杂 schema。

4. 失败优先于假成功。
   - 如果调用表达式解析失败或参数超出 bounded subset，必须产生 `unsupported_syntax` 并不生成 Rust draft。

## Risks / Trade-offs

- [Risk] 过度接受未知 callee 可能让语义等价看起来比实际更强。Mitigation: evidence 只声明 direct callee 被记录，不声明 callee 语义已验证。
- [Risk] 简单字符串 parser 误识别复杂表达式。Mitigation: 只接受 callee 为 identifier、括号匹配、参数列表可安全拆分的窄模式。
- [Risk] 与 simple call statement 规则重复。Mitigation: statement 继续用 `simple-call`，expression 位置使用 `bounded-call-expression`。

## Migration Plan

1. 增加 failing translator tests，证明当前 call expression 没有结构化 evidence。
2. 实现 direct call expression parser 和 statement annotation。
3. 将规则记录到 CFG/plan，并保持 Rust 输出不退化。
4. 运行 translator tests、OpenSpec strict/all、短验证命令后再考虑接入更高层 auto evidence。
