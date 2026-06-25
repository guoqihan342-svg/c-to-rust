## Why

当前 translator 已能保留 `observe(value);` 这类 simple call statement，但 `return helper(value);`、`int y = helper(value);`、`y = helper(value);` 这类 call expression 只是碰巧作为字符串穿过 `translate_expr`，没有结构化记录 callee、参数形态和翻译规则。进入跨文件深度关联上下文管理后，调用表达式必须成为可验证 evidence，而不能只依赖 Rust 字符串输出。

## What Changes

- 为受限 direct call expression 增加结构化识别：callee 必须是普通标识符，参数必须是当前 bounded expression 子集。
- 在 CFG statement kinds、translation rule ids、auto-translation plan/context evidence 中记录 call expression，而不只记录 simple call statement。
- 支持 `return helper(x);`、primitive declaration initializer、assignment RHS 三个主路径。
- 对函数指针调用、成员函数式调用、宏展开调用、side-effect 参数、unknown callee 语义和跨文件函数体内联保持阻断或非目标声明。
- 保持默认 safe Rust；不为调用表达式引入新的 first-party unsafe。

## Capabilities

### New Capabilities

### Modified Capabilities
- `bounded-auto-translation-pipeline`: 增加 bounded direct call expression 的翻译、callee evidence 和阻断规则。

## Impact

- `crates/c2r-translator/src/lib.rs`: 增加 call expression 分类、callee evidence、规则记录和受限表达式校验。
- `crates/c2r-translator/tests/bounded_translation.rs`: 增加红绿测试，覆盖 return/declaration/assignment call expression 与 unsupported call forms。
- `validation/tools/auto_migrate.py`: 如 translator 输出新增 call expression evidence，确保 context pack/CFG/plan 中保留 direct callee 信息。
- `openspec/specs/bounded-auto-translation-pipeline`: 归档后更新自动翻译管线要求。
