## Context

`c2r-translator` 已能翻译 primitive declaration、plain assignment、return、simple call、if/while/for 和部分 pointer out-param。当前 `value += 1;` 被分类为 `Expression` 并触发 unsupported guard；`i++`、`--i` 作为 standalone 语句也会被拒绝。与此同时，for-loop step 已经有 `translate_for_step()` 能把 `i++` 转为 `i += 1`，说明该语义可安全作为 statement lowering 支持。

## Goals / Non-Goals

**Goals:**
- 支持 standalone compound assignment 语句并生成等价 Rust compound assignment。
- 支持 standalone pre/post increment 和 decrement 语句并生成 `+= 1` 或 `-= 1`。
- 为这些语句记录 CFG statement kind 和 translation rule id。
- 保持未知 expression 的 blocked 行为。

**Non-Goals:**
- 不支持 compound assignment 作为表达式值使用，例如 `return (x += 1)`。
- 不支持 comma expression、ternary expression、macro-expanded side effect 或 volatile 语义。
- 不改变 pointer ownership、safe wrapper 或 oracle acceptance 策略。
- 不扩大到 goto/switch/relooper。

## Decisions

1. 新增 statement-level parser，而不是让 `translate_expr()` 猜测。
   Rationale: 当前 translator 的安全边界是 statement classification 先决定是否可翻译。把 compound support 放在 classify/emit 路径中，可以继续让未知 expression blocked。
   Alternative considered: 在 `translate_expr()` 中直接替换 `++` 或 `+=`。Rejected because it would silently accept expression contexts that may have C value semantics.

2. 用独立 `StatementKind` 区分 compound assignment 和 inc/dec。
   Rationale: 这样 CFG evidence 和 translation rule ids 能清楚说明新能力来自哪条规则，后续 validators 可追踪。
   Alternative considered: 复用 `Assignment`。Rejected because `parse_assignment()` 的 plain assignment 规则故意跳过复合运算符。

3. 支持 Rust 原生可表达的复合赋值运算符；typed IR / clang-lowered 路径额外支持 clang 已证明的窄化整数 promotion/truncation，但不做完整 usual arithmetic conversions 推断。
   Rationale: 受限 translator 生成 draft candidate，语义接受仍由 oracle/diff gates 决定。这个 change 只声明语法 lowering 和 clang-proven narrow cast lowering，不声明 C integer promotion 完整等价。

## Risks / Trade-offs

- [Risk] C integer promotion 和 Rust 运算类型规则可能在窄整数上不同。-> Mitigation: 只有 clang 已给出 target/result 与 compute 类型且 guard 可证明时才显式 cast；semantic pass 仍必须经过 oracle/replay/diff。
- [Risk] `x++` 在 C 表达式上下文有返回旧值语义。-> Mitigation: 只支持 standalone statement，不支持 expression context。
- [Risk] 过宽的 parser 误接收复杂 lvalue。-> Mitigation: 复用 simple target 检查，并保留 unsupported tests。

## Migration Plan

1. 新增红灯 translator tests。
2. 实现 statement classification、emission 和 rule evidence。
3. 更新旧 unsupported test，使它覆盖仍然不支持的表达式。
4. 跑 translator tests、auto_migrate tests、OpenSpec、full regression smoke。
