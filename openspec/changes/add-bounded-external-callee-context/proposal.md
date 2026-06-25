## Why

当前 `demo-call-expression` 为了让 generated Rust draft 能 standalone `rustc`，使用了 self-recursive call expression，仍然没有解决真实 C slice 常见的外部 helper callee。为了推进“跨文件深度关联性上下文管理”，需要让 spec 显式声明的一层 direct helper callee 能进入 context pack、translation plan、Rust draft check 和 L3 evidence。

## What Changes

- 新增受限 external direct callee context 能力：slice spec 可声明 helper callee 的签名和 bounded C source。
- `auto_migrate` 在生成 Rust draft 后，为 spec 声明且被 call-expression evidence 引用的 helper callee 注入安全 Rust stub/translation，使 draft 能 standalone rust-check。
- context pack、translation plan、test translation 和 final manifest 必须记录 callee 来源、边界和未声明 callee 的阻断状态。
- 新增 `demo-external-direct-callee` L3 slice，用 `call_helper_chain(value)` 调用 `helper_add_one(value)` 覆盖 declaration initializer、assignment RHS、return expression。
- 不声明任意跨文件函数体内联、多层调用图、函数指针、宏调用、可变参数、状态ful helper 或别名语义已解决。

## Capabilities

### New Capabilities
- `bounded-external-callee-context`: 描述显式声明的一层 direct helper callee 如何进入上下文、Rust draft 和 L3 evidence。

### Modified Capabilities
- `bounded-auto-translation-pipeline`: auto pipeline 必须在 accepted evidence binding 中保留 declared direct callee context，并在 missing/unsupported callee 时阻断 semantic pass。

## Impact

- `crates/c2r-translator/` 或 `validation/tools/auto_migrate.py`: 增加 declared helper callee stub/translation 的最小生成路径。
- `validation/slice-specs/`: 新增 `demo-external-direct-callee.json`，声明 caller/helper 边界。
- `validation/l2_slices/`: 新增 C oracle generator、fixture、Rust replay test 和 safe Rust report API。
- `validation/l2_slices/src/bin/emit_reports.rs`: 新增 direct L3 evidence、negative diff、unsafe evidence、summary 和 manifest。
- `validation/tools/`: 新增/扩展 auto evidence validator 测试，确保 direct callee context 不丢失。
- `scripts/run-full-regression.ps1`: 新增 `demo-external-direct-callee-auto-evidence-semantic` step。
