## 110. 2026-06-27 compound-body multi VarDecl expansion

本轮继续拓展 `c2r-translator` 的 clang-lowered typed IR candidate generation，不写 FlashDB 专用分支。切片目标是支持普通 compound body 中一个 `DeclStmt` 含多个简单 `VarDecl` 的真实 clang AST 形态，例如：

```c
int multi_decl(void) {
    int a = 1, b = 2;
    return a + b;
}
```

现在会 lower 成连续 typed IR 声明，并由 generic emitter 生成可编译 Rust：

```rust
let mut a: i32 = 1i32;
let mut b: i32 = 2i32;
return (a + b);
```

核心改动：
- `crates/c2r-translator/src/clang_frontend.rs`
  - `compound_body_skeleton_from_ast()` 改为一对多展开 body statement。
  - 新增 `body_stmt_skeletons_from_ast()`，仅对普通 compound body 中的 `DeclStmt` 展开多个 `VarDecl`。
  - 新增 `var_decl_skeleton_from_ast()`，复用原单 `VarDecl` 的 name/type/init 逻辑。
  - `decl_stmt_skeleton_from_ast()` 仍是 singular API；`for_init_stmt_skeleton_from_ast()` 继续调用它，所以 `for (int i = 0, j = 0; ...)` 保持 fail-closed。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - `clang_ast_dump_emits_multi_var_decl_stmt_when_enabled`
  - `clang_ast_dump_rejects_typed_ir_for_multi_var_decl_init_when_enabled`
- `crates/c2r-translator/src/clang_frontend.rs` tests
  - `compound_body_skeleton_from_ast_expands_multi_var_decl_stmt`
- 双语/设计文档同步：
  - `docs/c2rust-migration-agent/README.md`
  - `docs/c2rust-migration-agent/README.en.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.en.md`
  - `codex/translator-strengthening-analysis.md`
  - `codex/translator-strengthening-analysis.en.md`
  - `docs/superpowers/plans/2026-06-27-multi-var-decl-expansion.md`

红灯已观察：

```powershell
$env:C2R_RUN_CLANG_AST_TESTS='1'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir multi_var_decl -- --nocapture
```

旧实现返回 `Unsupported { reason: "DeclStmt with 2 VarDecl children..." }`，不能把一个 clang `DeclStmt` 展开为连续声明。

聚焦验证已通过：

```powershell
$env:C2R_RUN_CLANG_AST_TESTS='1'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir multi_var_decl -- --nocapture
```

边界：
- 可以说：普通 compound body 中多个简单 `VarDecl` 现在按源码顺序展开为连续 typed IR `Decl`，并可由 generic emitter 生成可编译 Rust candidate。
- 不应说：已支持 `ForStmt` init 多声明、所有 declaration statement、无初始化普通声明、unsupported type/initializer、VLA/incomplete array、重复符号恢复、完整 C scope/semantic acceptance。

下一步建议：
- 继续扩普通声明/表达式覆盖时，可选切片是 `for` init 多声明的 scoped model，或者 `break` / `continue` 语义；不要混进 pointer/alias 语义。

English mirror summary:

- Added clang-frontend expansion for ordinary compound-body `DeclStmt` nodes that contain multiple simple `VarDecl` children.
- `int a = 1, b = 2; return a + b;` now lowers to consecutive typed IR declarations and emits compilable Rust through the generic emitter.
- The expansion is intentionally limited to ordinary compound bodies. Multi `VarDecl` in `ForStmt` init still uses the singular init parser and remains fail-closed.
- Unsupported VarDecl types, unsupported initializers, VLA or incomplete arrays, missing initializer children, multiple initializer children, uninitialized ordinary declarations, duplicate symbols, and full semantic acceptance are still out of scope.
- Unit skeleton coverage and real clang AST smoke coverage pass for this slice.

## 111. 2026-06-27 assigned-before-read uninitialized scalar locals

本轮继续拓展 `c2r-translator` 的 generic typed IR emitter，不写 FlashDB 专用分支。切片目标是支持普通标量局部变量先声明、后赋值、再读取的真实 C 形态，例如：

```c
int assign_after_decl(void) {
    int tmp;
    tmp = 7;
    return tmp;
}
```

现在会由 clang AST lower 成：

```text
Decl(tmp, init=None)
Assign(tmp = 7)
Return(tmp)
```

并由 typed IR generic emitter 发射成可编译 Rust：

```rust
let mut tmp: i32;
tmp = 7i32;
return tmp;
```

核心改动：
- `crates/c2r-translator/src/typed_ir.rs`
  - 新增 `DefiniteAssignmentState`，在 Rust 发射前运行保守 definite-assignment guard。
  - 参数和 readonly globals 视为已声明且已初始化。
  - `Decl(init=None)` 只声明、不初始化；`Assign` 先验证 RHS 中没有读取未初始化标量，再把 target 标为 initialized。
  - guard 只跟踪当前 generic emitter 能发射的标量类型，避免抢走 pointer/array/unsupported type 原本更精确的 fail-closed reason。
  - 普通 scalar `Decl(init=None)` 现在发射 `let mut name: Ty;`；array/pointer/record/function 等仍由既有类型门禁拒绝。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - `typed_ir_emits_uninitialized_local_decl_assigned_before_read`
  - `typed_ir_rejects_uninitialized_local_decl_read_before_assignment`
  - `clang_ast_dump_emits_uninitialized_local_decl_assigned_before_read_when_enabled`
- 双语/设计文档同步：
  - `docs/c2rust-migration-agent/README.md`
  - `docs/c2rust-migration-agent/README.en.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.en.md`
  - `codex/translator-strengthening-analysis.md`
  - `codex/translator-strengthening-analysis.en.md`
  - `docs/superpowers/plans/2026-06-27-uninitialized-local-decl.md`

红灯已观察：

```powershell
$env:C2R_RUN_CLANG_AST_TESTS='1'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir uninitialized_local_decl -- --nocapture
```

旧实现中两个正测失败在 `stmt[0].decl tmp without initializer is unsupported`，说明 clang frontend 已能 lower，但 generic emitter 全局拒绝无 initializer 声明。

调试记录：
- 首版 guard 曾抢先拒绝 pointer/unsupported-type 负测，改变旧的精确错误原因。
- 修正后 guard 仅跟踪可发射标量类型；pointer/array/unsupported expression 继续交给原有 emitter 子集判断。
- 嵌套 body 的错误路径也对齐原 emitter 的 `while body[0]` / `if else[0]` 格式。

聚焦验证已通过：

```powershell
$env:C2R_RUN_CLANG_AST_TESTS='1'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir uninitialized_local_decl -- --nocapture
```

完整验证已通过：

```powershell
cargo fmt --manifest-path .\crates\c2r-translator\Cargo.toml -- --check
$env:C2R_RUN_CLANG_AST_TESTS='1'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir,clang-lowering-report -- --nocapture
```

结果：`src/lib.rs` 42 passed，`bounded_translation.rs` 319 passed。

边界：
- 可以说：普通标量局部 `int tmp; tmp = 7; return tmp;` 现在可经真实 clang AST + typed IR generic emitter 生成可编译 Rust candidate。
- 可以说：`int tmp; return tmp;` 继续 fail closed，reason 中会指出 `tmp` 读取前未赋值。
- 不应说：已支持完整 C definite assignment、默认零初始化、address-taken initialization、间接写入、alias write、loop-only initialization、所有 branch-sensitive initialization、数组无 initializer、pointer/record/function 无 initializer、完整 semantic acceptance。

下一步建议：
- 继续扩大普通 C 语法面时，优先候选是 `for` init 多声明的 scoped model，或更系统的 usual conversion 分类；`break` / `continue` 需要先设计 `for` step 语义，不能直接发 Rust `continue;`。

English mirror summary:

- Added conservative assignment-before-read support for uninitialized scalar local declarations in the generic typed IR emitter.
- `int tmp; tmp = 7; return tmp;` now lowers through real clang AST to `Decl(init=None)`, `Assign`, `Return`, and emits compilable Rust with `let mut tmp: i32;`.
- The pre-emission guard tracks only scalar types that the generic emitter can emit, so pointer/array/unsupported-type cases keep their existing fail-closed reasons.
- Reads before assignment still fail closed; this is not default zero initialization and not full C definite-assignment analysis.
- Focused real-clang smoke coverage and the full `clang-frontend,typed-ir,clang-lowering-report` gate pass for this slice.

## 112. 2026-06-27 scoped ForStmt init multi VarDecl expansion

本轮继续按多智能体并行推进 `c2r-translator` 的真实 C 语法面，不写 FlashDB 专用路径。切片目标是把真实 clang AST 中常见的 `ForStmt` init 多声明从 fail-closed 推进到 generic typed IR candidate generation，例如：

```c
int sum_pair_for(int limit) {
    int total = 0;
    for (int i = 0, j = 0; i < limit; i++) {
        total = total + i + j;
    }
    return total;
}
```

核心改动：
- `crates/c2r-translator/src/typed_ir.rs`
  - `IrStmt::For.init` 从 `Option<Box<IrStmt>>` 改成 `Vec<IrStmt>`。
  - `emit_for_stmt()` 在现有 Rust block + `while` 形态里按源码顺序发射每条 init statement。
  - definite-assignment、byte-cursor source、post-increment byte read、nullable pointer、assigned-var 等递归 helper 现在遍历 `init: &[IrStmt]`。
  - `step` 仍保持单语句 `Option<Box<IrStmt>>`，避免把这刀扩大成完整 C for-loop 语义。
- `crates/c2r-translator/src/clang_frontend.rs`
  - `ClangStmtSkeleton::For.init` 从 singular optional stmt 改成 `Vec<ClangStmtSkeleton>`。
  - 新 `for_init_stmt_skeletons_from_ast()` 对 `DeclStmt` 复用普通 compound body 的 multi-`VarDecl` 展开 helper；assignment init 仍包成一元素 vec；其他 init kind 继续 fail closed。
  - `lower_stmt()` 把 skeleton init vec 逐条 lowering 成 typed IR init vec，任何 unsupported declarator 都会让整个 For lowering fail closed。
- `crates/c2r-translator/src/lib.rs`
  - clang-lowering report 的 type mapping、call expression evidence、pointer cursor source、post-increment deref evidence 递归遍历 For init vec。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 将真实 clang multi-`VarDecl` For init smoke 从 reject 改为 positive：
    `clang_ast_dump_emits_typed_ir_for_multi_var_decl_init_when_enabled`。
  - 新增 direct typed IR 正测：
    `typed_ir_for_emits_scoped_loop_with_multi_decl_init`。
  - 既有 direct/skeleton/real-clang For 测试改为 `init: vec![...]` / `init.as_slice()` 断言。
  - 真实 clang positive 现在断言 top-level body 为 `[Decl(total), For { init: [Decl(i), Decl(j)], step: Assign, body: [Assign] }, Return]`，并验证生成 Rust 可编译。
- 双语文档同步：
  - `docs/c2rust-migration-agent/README.md`
  - `docs/c2rust-migration-agent/README.en.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.en.md`
  - `codex/translator-strengthening-analysis.md`
  - `codex/translator-strengthening-analysis.en.md`
  - `docs/superpowers/plans/2026-06-27-for-init-multi-var-decl.md`

红灯已观察：

```powershell
$env:C2R_RUN_CLANG_AST_TESTS='1'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir multi_var_decl_init -- --nocapture
```

旧实现中 positive smoke 失败为 `report.status == "unsupported"`，reason 为 `DeclStmt with 2 VarDecl children is outside the current clang lowering skeleton`。

聚焦验证已通过：

```powershell
$env:C2R_RUN_CLANG_AST_TESTS='1'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir multi_var_decl_init -- --nocapture
cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features typed-ir typed_ir_for_emits_scoped_loop_with_multi_decl_init -- --nocapture
```

完整验证已通过：

```powershell
cargo fmt --manifest-path .\crates\c2r-translator\Cargo.toml -- --check
git diff --check
$env:C2R_RUN_CLANG_AST_TESTS='1'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir multi_var_decl_init -- --nocapture
$env:C2R_RUN_CLANG_AST_TESTS='1'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir,clang-lowering-report -- --nocapture
```

结果：聚焦真实 clang smoke 1 passed；完整 feature gate 中 `src/lib.rs` 42 passed，`bounded_translation.rs` 320 passed，doc-tests 0 passed。`git diff --check` exit 0，仅报告 Windows LF/CRLF 提示。

边界：
- 可以说：普通 compound body 和 scoped `ForStmt` init 中多个简单 `VarDecl` 现在都能按源码顺序展开为连续 typed IR `Decl`，并可由 generic emitter 生成可编译 Rust candidate。
- 可以说：`ForStmt` init 多声明的 scope 由一等 `IrStmt::For { init: Vec<IrStmt>, ... }` 保住，init 声明不泄漏到 loop block 外，body-local 声明不泄漏到 step。
- 不应说：已支持复杂 init/step、`continue` / `break` / `goto` / `switch`、condition variable slot、空 condition/step、prefix inc/dec step、任意 declaration statement、unsupported type/initializer、VLA/incomplete array、重复符号恢复、完整 C for-loop control-flow semantics 或 semantic acceptance。

下一步建议：
- 继续扩大普通 C 语法面时，优先候选是更系统的 usual scalar conversion 分类，或在已有 scoped `ForStmt` 上单独设计 `break` / `continue` 的 step 语义、CFG evidence 和 validation gate。
- 第 110/111 节里“for init 多声明 scoped model”作为下一步建议已被本节 supersede。

English mirror summary:

- Added scoped `ForStmt` init multi-`VarDecl` expansion through generic typed IR.
- `IrStmt::For.init` and `ClangStmtSkeleton::For.init` are now ordered vectors; `step` remains singular.
- `for (int i = 0, j = 0; i < limit; i++)` lowers from real clang AST to `For { init: [Decl(i), Decl(j)], ... }` and emits compilable Rust in source order inside the loop block.
- Unsupported declarator types/initializers, VLA/incomplete arrays, duplicate symbols, complex init/step, missing condition/step, condition variable slots, `continue` / `break`, full C for-loop control-flow semantics, and semantic acceptance remain out of scope.
- Focused red/green coverage, direct typed IR coverage, real clang AST smoke coverage, and the full `clang-frontend,typed-ir,clang-lowering-report` gate pass for this slice.

## 113. 2026-06-27 loop-body break and signed-char promotion slice

本轮继续按多智能体推进 `c2r-translator` 的核心语法面，不写 FlashDB 专用路径。两个只读子智能体分别复核了 usual scalar conversion 的真实边界和测试/doc 缺口；主线程落地两个小切片：

1. loop body `break`：真实 clang `BreakStmt` 现在能 lowering 成 `IrStmt::Break`，generic typed IR emitter 只在 `while` / scoped `ForStmt` body 内发射 Rust `break;`。顶层或非 loop 上下文的 `break` 继续 fail closed。
2. 精确 `signed char` promotion：`type_from_qual_type()` 现在识别精确 `signed char` spelling 为 signed 8-bit integer。普通二元整数运算 operand 上，如果 clang 已保留 `IntegralCast` / `IntegralPromotion`，typed emitter 继续要求 cast 后 lhs/rhs/result 类型严格对齐后再发射，例如 `signed char value + 1` 发射 `((value as i32) + 1i32)`。

核心改动：
- `crates/c2r-translator/src/typed_ir.rs`
  - 新增 `IrStmt::Break`。
  - `emit_stmt()` 增加 loop 上下文参数；`while` / `For` body 传入 `in_loop=true`，top-level、for init 和 for step 仍传入 `false`。
  - definite-assignment、post-increment byte read、nullable pointer use 等只读遍历补上 `Break` 分支。
- `crates/c2r-translator/src/clang_frontend.rs`
  - `ClangStmtSkeleton::Break`、`BreakStmt` skeleton lowering、`lower_stmt()` 到 `IrStmt::Break`。
  - `type_from_qual_type("signed char")` 精确映射为 signed 8-bit integer；`short` / `long long` 等其他 target-dependent spelling 仍 unsupported。
- `crates/c2r-translator/src/lib.rs`
  - clang-lowering report/evidence 的只读 IR 遍历补上 `Break`：call evidence 跳过，statement label/kind 记录为 `break`，post-increment evidence 跳过。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - direct typed IR：`typed_ir_emits_break_in_scalar_while_body`、`typed_ir_rejects_break_outside_loop`、`typed_ir_emits_binary_arithmetic_with_integral_operand_cast`。
  - real clang smoke：`clang_ast_dump_emits_typed_ir_while_break_when_enabled`、`clang_ast_dump_emits_signed_char_binary_promotion_when_enabled`。
- 文档同步：
  - `docs/c2rust-migration-agent/README.md`
  - `docs/c2rust-migration-agent/README.en.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.en.md`
  - `codex/translator-strengthening-analysis.md`
  - `codex/translator-strengthening-analysis.en.md`

验证已通过：
```powershell
cargo fmt --manifest-path 'F:\agent\crustpaper\0625ctr\crates\c2r-translator\Cargo.toml' -- --check
git diff --check
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:/Program Files/LLVM/bin/clang.exe'; cargo test --manifest-path 'F:\agent\crustpaper\0625ctr\crates\c2r-translator\Cargo.toml' --features clang-frontend,typed-ir,clang-lowering-report -- --nocapture
```

结果：`src/lib.rs` 43 passed，`bounded_translation.rs` 325 passed，doc-tests 0 passed。`git diff --check` exit 0，仅报告 Windows LF/CRLF 提示。

边界：
- 可以说：`while` / scoped `ForStmt` body 中的 `break` 现在可经真实 clang AST + typed IR generic emitter 生成可编译 Rust candidate。
- 可以说：精确 `signed char` 可作为 signed 8-bit integer 进入 typed IR，并能通过 clang-preserved integral promotion cast 支持普通二元整数运算小切片。
- 不应说：已支持 `continue`、`goto`、`switch`、`do-while`、完整 C for-loop control-flow semantics、plain `char`、plain `long`、`short` / `long long` target ABI 宽度推断、完整 usual scalar conversions、side-effect-heavy operand 或 semantic acceptance。

下一步建议：
- 继续 usual scalar conversion 分类，但仍只接受 clang 已显式证明的 integral cast / promotion 小切片，不要自行推断完整 C conversion。
- 或继续控制流：优先设计 `continue` 的 for-step 语义，不能直接发 Rust `continue;`，因为当前 `ForStmt` lowering 把 step 放在 while body 尾部。

English mirror summary:

- Added loop-body `break` support through clang skeleton, typed IR, and the generic emitter.
- `BreakStmt` lowers to `IrStmt::Break`; the emitter only emits Rust `break;` in loop contexts, and rejects top-level/non-loop `break`.
- Added exact `signed char` type support as signed 8-bit integer, enabling clang-proven ordinary binary promotion such as `signed_char_add_one(signed char value) { return value + 1; }`.
- This remains candidate generation only. `continue`, `goto`, `switch`, `do-while`, full C for-loop control-flow semantics, plain `char`, plain `long`, `short` / `long long` ABI width inference, complete usual scalar conversions, side-effect-heavy operands, and semantic acceptance still fail closed.
- The full `clang-frontend,typed-ir,clang-lowering-report` gate passes: 43 lib tests, 325 bounded translation tests, and 0 doc-tests.

## 114. 2026-06-27 loop-body continue and competition environment profile

本轮继续按多智能体推进 `c2r-translator` 核心语法面，并补入比赛环境硬约束。两个只读子智能体先复核 `continue` 的实现风险和文档缺口；后续只读子智能体复核比赛环境 profile 应接入的验证位置。第 113 节中“`continue` 仍 fail closed / 下一步设计 continue for-step 语义”的表述已被本节 supersede。

核心翻译改动：
- `crates/c2r-translator/src/typed_ir.rs`
  - 新增 `IrStmt::Continue`。
  - `emit_stmt()` 的 loop 参数从 `bool` 升级为 `LoopContext`：`None`、`While`、`For { step }`。
  - `while` body 中的 `continue` 直接发射 Rust `continue;`。
  - scoped `ForStmt` body 中的 `continue` 会先发射当前简单 step，再发射 Rust `continue;`，避免当前 `ForStmt -> block + while + body + step` lowering 跳过 C for-step。
  - 嵌套循环会覆盖 loop context，所以内层 `while` 的 `continue` 不会执行外层 `ForStmt` step。
  - 顶层或非 loop 上下文的 `continue` 继续 fail closed。
  - definite-assignment、post-increment byte read、nullable pointer use 等只读遍历补上 `Continue` 分支。
- `crates/c2r-translator/src/clang_frontend.rs`
  - 新增 `ClangStmtSkeleton::Continue`。
  - `ContinueStmt` skeleton lowering 到 `ClangStmtSkeleton::Continue`，再 lowering 到 `IrStmt::Continue`。
- `crates/c2r-translator/src/lib.rs`
  - clang-lowering report/evidence 的只读 IR 遍历补上 `Continue`：call evidence 跳过，statement label/kind 记录为 `continue`，post-increment evidence 跳过。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 direct typed IR 正/负测：`typed_ir_emits_continue_in_scalar_while_body`、`typed_ir_for_emits_continue_after_step_in_body`、`typed_ir_for_nested_while_continue_does_not_emit_outer_step`、`typed_ir_rejects_continue_outside_loop`。
  - 新增/转换真实 clang smoke：`clang_ast_dump_emits_typed_ir_for_continue_when_enabled`、`clang_ast_dump_emits_typed_ir_while_continue_when_enabled`。

比赛环境配置：
- 新增 `validation/environment-profiles/huawei-competition-ubuntu-24.04/` 作为单一环境 profile。
- `environment.json` 记录 Ubuntu 24.04.4 LTS、kernel `5.10.0-182.0.0.95.r194_123.hce2.x86_64`、华为 APT/PyPI/npm/Cargo mirror、Python 3.12.3、pip 24.0、Node v24.13.0、npm 11.6.2、OpenJDK 21.0.10 Bisheng、Maven 3.9.11、`MAVEN_HOME=/usr/local/maven3`、Rust/Cargo 1.96.0、gcc/g++ 13.3.0、GNU Make 4.3，并显式记录 Go 未安装、CMake 未找到。
- 附带 `apt/sources.list`、`pip/pip.conf`、`npm/.npmrc`、`cargo/config.toml`、`rust/rust-toolchain.toml`、`env.sh` 和 `toolchain-check.sh`。
- `validation/gates.md` 要求 L1/L3 在比赛/evaluation host 上记录 environment profile path/hash。
- `validation/l3-template/config-profile.schema.json` 新增可选 `environment_profile` 绑定；example 加入 placeholder。
- `scripts/run-full-regression.ps1` 新增 `-EnvironmentProfile` 参数，默认指向该 profile；`events.jsonl` 和 `summary.json` 会写出 `profile_id/path/sha256`。脚本内部 PowerShell 子调用改为复用当前 PowerShell 可执行文件路径，避免 Ubuntu 上硬编码 `powershell`。
- `validation/README.md`、`docs/c2rust-migration-agent/README*.md`、`build-and-c2rust-baseline.md`、`full-regression-runner.md` 已同步说明比赛环境边界：默认 gate 不依赖 Go/CMake，优先 Cargo/Python/gcc/g++/GNU Make。

验证已通过：
```powershell
cargo fmt --manifest-path 'F:\agent\crustpaper\0625ctr\crates\c2r-translator\Cargo.toml' -- --check
git diff --check
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:/Program Files/LLVM/bin/clang.exe'; cargo test --manifest-path 'F:\agent\crustpaper\0625ctr\crates\c2r-translator\Cargo.toml' --features clang-frontend,typed-ir,clang-lowering-report -- --nocapture
python -m json.tool validation/environment-profiles/huawei-competition-ubuntu-24.04/environment.json
python -m json.tool validation/l3-template/config-profile.schema.json
python -m json.tool validation/l3-template/config-profile.example.json
bash -n validation/environment-profiles/huawei-competition-ubuntu-24.04/env.sh
bash -n validation/environment-profiles/huawei-competition-ubuntu-24.04/toolchain-check.sh
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-full-regression.ps1 -Rounds 1 -StartRound 2 -SkipLongStress -SkipClippy -EvidenceRoot target/full-regression-syntax -RunId env-profile-smoke
```

结果：`src/lib.rs` 43 passed，`bounded_translation.rs` 330 passed，doc-tests 0 passed。`git diff --check` exit 0，仅报告 Windows LF/CRLF 提示。`run-full-regression.ps1` 零步 smoke 成功写出 environment profile `profile_id/path/sha256`。

边界：
- 可以说：`while` / scoped `ForStmt` body 中的窄化 `continue` 现在可经真实 clang AST + typed IR generic emitter 生成可编译 Rust candidate。
- 可以说：同一层 `ForStmt` body 的 `continue` 会先执行 step；嵌套循环的 `continue` 不会误执行外层 step。
- 可以说：比赛环境 profile 已有单一配置目录和可追溯 profile hash 绑定入口。
- 不应说：已支持 `goto`、`switch`、`do-while`、condition variable slot、空 condition/step、复杂 init/step、prefix inc-dec step、完整 C for-loop control-flow semantics、完整 semantic acceptance，或默认比赛环境支持 Go/CMake。

English mirror summary:

- Added narrow loop-body `continue` support through clang skeleton, typed IR, and the generic emitter.
- `ContinueStmt` lowers to `IrStmt::Continue`; `while` emits Rust `continue;`; scoped `ForStmt` emits the current step before Rust `continue;`; nested-loop `continue` targets only the inner loop.
- Added direct typed IR and real clang smoke coverage for while continue, for continue step ordering, nested-loop targeting, and non-loop fail-closed behavior.
- Added `validation/environment-profiles/huawei-competition-ubuntu-24.04/` as the single competition environment profile, including mirrors, tool versions, Go/CMake absence, and shell self-checks.
- Full translator gate passes with real clang enabled: 43 lib tests, 330 bounded translation tests, and 0 doc-tests.

## 115. 2026-06-27 narrow DoStmt / do-while typed IR support

本轮继续按多智能体推进 `c2r-translator` 的通用语法面。三个只读子智能体分别复核 typed IR emitter、clang frontend lowering 和文档/验证路线；结论一致：当前下一刀最合适的是 `DoStmt` / `do-while`，因为它复用现有 condition emitter、loop-body `break` / `continue` 语义和 clang AST 入口，同时比 `switch` / `goto` 的 CFG/relooper 问题更可控。第 114 节中“`do-while` 仍未支持”的边界被本节 supersede。

核心翻译改动：
- `crates/c2r-translator/src/typed_ir.rs`
  - 新增 `IrStmt::DoWhile { body, condition, source_span }`。
  - `LoopContext` 新增 `DoWhile { condition }`，用于 body 内 `continue` 的正确 lowering。
  - `DoWhile` 发射为 Rust `loop { ... if !(condition) { break; } }`，保留 C `do-while` body 至少执行一次的形态。
  - `DoWhile` body 中的 `continue` 会先发射同一个 condition break check，再发射 Rust `continue;`，避免 Rust `continue` 直接跳回 loop 顶部而跳过 C 的尾部 condition。
  - definite-assignment、byte cursor source、post-increment byte read、nullable pointer collect/validate、assigned var 推断等只读遍历补上 `DoWhile` 分支。
- `crates/c2r-translator/src/clang_frontend.rs`
  - 新增 `ClangStmtSkeleton::DoWhile`。
  - `stmt_skeleton_from_ast()` 支持 `DoStmt`。
  - 新增 `do_stmt_skeleton_from_ast()`，按 clang JSON 的 `[body, condition]` 子节点顺序 lowering。
  - `lower_stmt()` 将 skeleton `DoWhile` lowering 成 typed IR `IrStmt::DoWhile`。
- `crates/c2r-translator/src/lib.rs`
  - clang-lowering report/evidence 的只读 IR 遍历补上 `DoWhile`：decl type mapping、call expression evidence、statement label/kind、CFG edge、pointer cursor source 和 post-increment deref evidence。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 direct typed IR 测试：
    - `typed_ir_emits_scalar_do_while_with_condition_check_after_body`
    - `typed_ir_do_while_continue_checks_condition_before_continuing`
  - 新增真实 clang AST smoke：
    - `clang_ast_dump_emits_typed_ir_do_while_when_enabled`

红灯已观察：
```powershell
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:/Program Files/LLVM/bin/clang.exe'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir do_while -- --nocapture
```

旧实现失败于：
- `no variant named DoWhile found for enum IrStmt`
- `DoStmt` 不在 clang skeleton lowering 中

focused 验证已通过：
```powershell
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:/Program Files/LLVM/bin/clang.exe'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir do_while -- --nocapture
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:/Program Files/LLVM/bin/clang.exe'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir,clang-lowering-report do_while -- --nocapture
```

focused 结果：3 个 do-while 测试通过；`clang-lowering-report` feature 下也通过，说明 evidence/report 的枚举穷尽分支已补齐。

文档同步：
- `docs/c2rust-migration-agent/core-translation-architecture.md`
- `docs/c2rust-migration-agent/core-translation-architecture.en.md`
- `codex/translator-strengthening-analysis.md`
- `codex/translator-strengthening-analysis.en.md`

边界：
- 可以说：窄化 clang `DoStmt` 现在可经真实 clang AST + typed IR generic emitter 生成可编译 Rust candidate。
- 可以说：`do-while` body 至少执行一次；尾部 condition 复用当前 `emit_condition_expr()` 支持的整数 truthiness、comparison、logical-not、readonly deref 等子集。
- 可以说：`do-while` body 中的 `continue` 会先检查 condition，再继续下一轮。
- 不应说：已支持完整 C loop control-flow semantics、`switch`、`goto`、condition 中 call/inc/dec/side effect、复杂 label/fallthrough/relooper、semantic acceptance 或任意 do-while condition。
- 后续建议：下一刀可按只读子智能体建议选 mutable pointer write 到 `&mut [T]` 的受限 lowering、nested pure direct call、step-position prefix inc/dec，或继续设计 `switch` / `goto`。

English mirror summary:

- Added narrow `DoStmt` / `do-while` support through clang skeleton, typed IR, and the generic emitter.
- `DoStmt` lowers to `IrStmt::DoWhile`; the emitter produces Rust `loop { ... if !(condition) { break; } }`.
- A `continue` inside a `DoWhile` body emits the same condition break check before Rust `continue;`, preserving C `do-while` condition semantics.
- Added direct typed IR coverage and a real clang AST smoke test for the do-while path.
- This is still candidate generation only. `switch`, `goto`, full loop control-flow semantics, side-effecting conditions, and semantic acceptance remain fail-closed.

## 116. 2026-06-27 ForStmt step-position prefix inc/dec and competition self-check tightening

本轮继续按多智能体推进 `c2r-translator` 的通用语法面，不写 FlashDB 专用代码。只读子智能体复核后确认：`for (...; ...; ++i)` / `--i` 的 step 表达式值被丢弃，对简单整数变量来说 prefix/postfix 的可观察差异只剩同一个 side effect，因此可以作为窄化 statement-position 切片放开。第 107、112、114、115 节中“prefix inc/dec step 仍不支持 / 是下一刀”的旧边界被本节 supersede。

核心翻译改动：
- `crates/c2r-translator/src/clang_frontend.rs`
  - 新增 `inc_dec_expr_skeleton_from_ast(expr, allow_prefix, preserve_integral_casts)`，让通用表达式入口继续 `allow_prefix=false`，而 `ForStmt` step 专用入口可传 `allow_prefix=true`。
  - `inc_dec_for_step_skeleton_from_ast()` 不再要求 postfix，只接受直接 `UnaryOperator` 的简单整数 `DeclRef` target，并 lowering 成 `ClangStmtSkeleton::Assign { value: Binary(Add/Sub, target, 1) }`。
  - `isPostfix` 必须是显式 bool；缺失或非 bool 会 fail closed，避免 AST 元数据不完整时把 step 当成 prefix 默认接受。
  - step helper 透传底层 unsupported reason，保留 fail-closed 诊断。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 原真实 clang prefix-step 负例改为正例：`clang_ast_dump_emits_typed_ir_for_prefix_increment_step_when_enabled`。
  - 新增真实 clang prefix decrement step 正例：`clang_ast_dump_emits_typed_ir_for_prefix_decrement_step_when_enabled`。
  - 新增真实 clang 负例，证明 value-position/call-argument prefix inc 仍拒绝：
    - `clang_ast_dump_rejects_prefix_increment_return_value_when_enabled`
    - `clang_ast_dump_rejects_prefix_increment_call_argument_when_enabled`
- `validation/environment-profiles/huawei-competition-ubuntu-24.04/toolchain-check.sh`
  - 比赛环境静态配置已覆盖用户补充的版本和镜像源。
  - 自检脚本补充完整 `VERSION=24.04.4 LTS (Noble Numbat)` 检查。
  - `java -version` 现在除 `21.0.10` 外，还大小写不敏感检查 `openjdk` 和 `bisheng`。

红灯已观察：
```powershell
cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir for_step_stmt_skeleton_from_ast_rejects_inc_dec_without_explicit_postfix_flag -- --nocapture
```

旧实现会把缺失 `isPostfix` 的 `++i` step 当成 assignment 接受；红测失败信息为 expected unsupported but got `Assign { ... }`。

focused 验证：
```powershell
cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir for_step_stmt_skeleton_from_ast -- --nocapture
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:/Program Files/LLVM/bin/clang.exe'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir prefix_ -- --nocapture
```

focused 结果：
- `for_step_stmt_skeleton_from_ast*`：4 passed。
- `prefix_`：`src/lib.rs` 4 passed，`bounded_translation.rs` 6 passed。

完整验证：
```powershell
cargo fmt --manifest-path .\crates\c2r-translator\Cargo.toml -- --check
bash -n validation/environment-profiles/huawei-competition-ubuntu-24.04/env.sh; bash -n validation/environment-profiles/huawei-competition-ubuntu-24.04/toolchain-check.sh
python -m json.tool validation/environment-profiles/huawei-competition-ubuntu-24.04/environment.json
git diff --check
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:/Program Files/LLVM/bin/clang.exe'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir,clang-lowering-report -- --nocapture
```

结果：`cargo fmt --check`、shell syntax、environment JSON、`git diff --check` 均 exit 0；`git diff --check` 仅报告 Windows LF/CRLF 提示。完整 translator gate 通过：`src/lib.rs` 48 passed，`bounded_translation.rs` 336 passed，doc-tests 0 passed。

文档同步：
- `docs/c2rust-migration-agent/core-translation-architecture.md`
- `docs/c2rust-migration-agent/core-translation-architecture.en.md`
- `docs/c2rust-migration-agent/README.md`
- `docs/c2rust-migration-agent/README.en.md`
- `codex/translator-strengthening-analysis.md`
- `codex/translator-strengthening-analysis.en.md`

边界：
- 可以说：`ForStmt` step-position 的简单整数变量 prefix `++i` / `--i` 现在可经真实 clang AST + typed IR generic emitter 生成可编译 Rust candidate。
- 可以说：该支持只利用 step expression 值被丢弃的事实，按 statement side effect 发射为 `i = i +/- 1`。
- 可以说：通用 expression path、return value、call argument、while/if/for condition、deref target、pointer target、缺失/非 bool `isPostfix` 元数据仍 fail closed。
- 不应说：已支持 value-position `++i` / `--i`、condition 中 inc/dec、副作用复杂 step、parenthesized/comma step、非简单整数变量 target、指针/数组/字段 inc-dec、完整 C for-loop control-flow semantics 或 semantic acceptance。
- 后续建议：下一刀优先考虑 mutable pointer write 到 `&mut [T]` 的受限 lowering、nested pure direct calls、generic inc/dec value semantics，或继续设计 `switch` / `goto`。

English mirror summary:

- Added narrow `ForStmt` step-position prefix `++i` / `--i` support for simple integer variable targets.
- The normal expression path still rejects prefix inc/dec; real clang tests cover return value, call argument, while condition, and deref fail-closed boundaries.
- Inc/dec clang JSON must carry an explicit boolean `isPostfix` field; missing or non-bool metadata fails closed.
- Tightened the Huawei competition environment self-check for full Ubuntu `24.04.4 LTS (Noble Numbat)` and Bisheng/OpenJDK Java provenance.
- Full translator gate passes with real clang enabled: 48 lib tests, 336 bounded translation tests, and 0 doc-tests.

## 117. 2026-06-27 typed IR mutable pointer output writes and standalone competition config

本轮继续按多智能体推进 `c2r-translator` 通用语法面，并按用户补充把比赛环境配置独立放到 `config/competition-env/`。三个只读子智能体分别评估了 mutable pointer write、nested direct calls、generic inc/dec value semantics；结论是 pointer output write 最贴近当前 P0 memory-model 缺口，nested call 可作为后续快刀，generic value-position inc/dec 暂不做泛化。第 116 节中“下一刀优先 mutable pointer write”的建议已被本节 supersede。

核心翻译改动：
- `crates/c2r-translator/src/typed_ir.rs`
  - 新增 `mutable_pointer_slice_element_type()` 和 `emit_assigned_param_type()`：只有函数参数作为写目标出现时，`T *out` 才发射为 `mut out: &mut [T]`；未使用或只读的 non-const pointer 仍 fail closed。
  - `emit_assignment_target()` 现在支持 mutable pointer 写目标：
    - `*out = value; -> out[0usize] = value;`
    - `out[i] = value; -> out[i as usize] = value;`
    - `*(out+i) = value;` / `*(i+out) = value; -> out[i as usize] = value;`
  - pointer-add 写 offset 复用 readonly offset read 的无副作用整数 index 边界：只接受 integer literal、var、cast；call、inc/dec、deref、binary compound index 等继续 fail closed。
  - definite-assignment 和 assigned-var 收集补上 `Deref` 写目标，因此 `*out` / `*(out+i)` 能把 `out` 识别为需要 `&mut [T]` 的参数。
  - 未声明 deref pointer 的旧负例仍 fail closed，但诊断从泛化的“assign target must be Var...”变成更具体的 `deref assignment pointer ptr is not declared`。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 direct typed IR 正测：
    - `typed_ir_emits_mutable_pointer_deref_assignment_as_mut_slice_zero_index`
    - `typed_ir_emits_mutable_pointer_index_assignment`
    - `typed_ir_emits_mutable_pointer_add_index_deref_assignment`
  - 新增 clang-lowered skeleton 正测：
    - `typed_ir_emits_mutable_pointer_index_assignment_from_clang_lowered_ir`
    - `typed_ir_emits_mutable_pointer_add_index_deref_assignment_from_clang_lowered_ir`
  - 新增真实 clang AST smoke：
    - `clang_ast_dump_emits_mutable_pointer_index_assignment_when_enabled`
    - `clang_ast_dump_emits_mutable_pointer_add_deref_assignment_when_enabled`
  - 新增/保留负测：`const T *` 写入、mutable pointer read、复杂 offset、未使用 mutable pointer param、readonly pointer offset call index 等继续 fail closed。

比赛环境配置改动：
- 新增 `config/competition-env/` 作为默认独立配置入口：
  - `environment.json`
  - `README.md` / `README.en.md`
  - `env.sh`
  - `toolchain-check.sh`
  - `apt/sources.list`
  - `pip/pip.conf`
  - `npm/.npmrc`
  - `cargo/config.toml`
  - `rust/rust-toolchain.toml`
- `scripts/run-full-regression.ps1` 默认 `-EnvironmentProfile` 改为 `config/competition-env/environment.json`。
- `validation/environment-profiles/huawei-competition-ubuntu-24.04/` 保留为历史 compatibility entrypoint，并在 `environment.json` 中声明 canonical path；README 中英文均已说明新默认路径。
- `validation/l3-template/config-profile.example.json` 示例 profile path 改为 `config/competition-env/environment.json`，示例 rust/cargo 版本改为 `1.96.0`。

文档同步：
- `docs/c2rust-migration-agent/core-translation-architecture.md`
- `docs/c2rust-migration-agent/core-translation-architecture.en.md`
- `docs/c2rust-migration-agent/README.md`
- `docs/c2rust-migration-agent/README.en.md`
- `docs/c2rust-migration-agent/full-regression-runner.md`
- `docs/c2rust-migration-agent/build-and-c2rust-baseline.md`
- `codex/translator-strengthening-analysis.md`
- `codex/translator-strengthening-analysis.en.md`
- `validation/README.md`
- `validation/gates.md`

红灯已观察：
```powershell
cargo test --features typed-ir typed_ir_emits_mutable_pointer --test bounded_translation
```

旧实现失败于：
- `stmt[0].assign target must be Var or local fixed array Index`
- `param out has pointer type int * is unsupported`

focused 验证：
```powershell
cargo test --features typed-ir typed_ir_emits_mutable_pointer --test bounded_translation
cargo test --features "typed-ir clang-frontend" mutable_pointer --test bounded_translation
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:/Program Files/LLVM/bin/clang.exe'; cargo test --features "typed-ir clang-frontend" mutable_pointer --test bounded_translation -- --nocapture
```

focused 结果：mutable pointer filter 下 10 条测试通过，包含 direct typed IR、clang-lowered skeleton、真实 clang AST smoke 和 fail-closed 边界。

完整验证：
```powershell
python -m json.tool config\competition-env\environment.json > $null
python -m json.tool validation\environment-profiles\huawei-competition-ubuntu-24.04\environment.json > $null
python -m json.tool validation\l3-template\config-profile.example.json > $null
bash -n config/competition-env/env.sh; bash -n config/competition-env/toolchain-check.sh
bash -n validation/environment-profiles/huawei-competition-ubuntu-24.04/env.sh; bash -n validation/environment-profiles/huawei-competition-ubuntu-24.04/toolchain-check.sh
cargo fmt -- --check
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:/Program Files/LLVM/bin/clang.exe'; cargo test --features "clang-frontend typed-ir clang-lowering-report" -- --nocapture
git diff --check
```

完整验证结果：
- config/profile JSON 校验通过。
- shell syntax 校验通过。
- `scripts/run-full-regression.ps1` PowerShell parser 静态检查通过。
- `cargo fmt --check` 通过。
- 完整 translator gate 通过：`src/lib.rs` 48 passed，`bounded_translation.rs` 345 passed，doc-tests 0 passed。
- `git diff --check` exit 0，仅报告 Windows LF/CRLF 提示。

边界：
- 可以说：函数参数 `T *out` 在作为写目标出现时，可经 direct typed IR、clang-lowered skeleton 和真实 clang AST 进入 `GenericTypedIr`，生成可编译 Rust `&mut [T]` slice assignment candidate。
- 可以说：支持的写形态是 `*out`、`out[i]`、`*(out+i)` / `*(i+out)`，元素类型必须是当前支持的整数标量，offset 必须是无副作用整数 literal/var/cast。
- 不应说：已支持 mutable pointer read、任意 pointer arithmetic、complex offset、compound/update write、nullable pointer write、pointer escape、多 mutable pointer alias/noalias 证明、volatile/hardware register、宏副作用或 semantic acceptance。
- 后续建议：下一刀优先 nested pure direct calls 或 standalone typed clang inc/dec statement；并行推进 struct/alias memory model 设计，避免把 `&mut [T]` 输出写误认为完整 C pointer ownership 模型。

English mirror summary:

- Added narrow mutable integer pointer output writes through the generic typed IR emitter.
- Function parameter `T *out` emits as `&mut [T]` only when it is used as a write target.
- Supported write forms are `*out`, `out[i]`, and `*(out+i)` / `*(i+out)`, emitted as Rust slice assignments.
- Direct typed IR, clang-lowered skeleton, real clang AST smoke, and fail-closed boundary tests cover the new path.
- Added standalone competition environment config under `config/competition-env/` and moved default validation/profile references to that path while keeping the old validation profile as a compatibility entrypoint.
- Full translator gate passes with real clang enabled: 48 lib tests, 345 bounded translation tests, and 0 doc-tests.

## 118. 2026-06-27 typed IR one-level nested direct calls and profile mirror checks

本轮继续按多智能体推进 `c2r-translator` 通用语法面，完成第 117 节建议的 nested pure direct call 快刀，并把用户补充的比赛环境约束核对到独立配置目录。四个只读子智能体分别给出结论：
- nested direct call：建议只放开“一层、一个、整个实参就是 direct call”，保留 deeper / multiple sibling / condition call / side-effect argument fail-closed。
- standalone typed clang inc/dec statement：当前真实 clang AST 还不支持普通 `value++; ++value;` statement；下一刀应复用 `ForStmt` step 的 inc/dec-to-Assign helper，只放开 statement value-discarded 场景。
- alias/memory model：mutable pointer output write 仍缺 noalias/ownership/length/effect graph 证明；下一阶段应先补 struct/alias memory model OpenSpec 和 pointer/slice evidence schema。本条关于 effect graph 生成的缺口已被第 122 节 supersede；完整 pointer ownership model 仍未完成。
- 比赛环境配置：`config/competition-env/` 已完整匹配用户给出的 Ubuntu 24.04.4、kernel、Huawei mirrors、Python/Node/Java/Maven/Rust/GCC/Make 和 Go/CMake 缺失事实；validation 侧目录只是 compatibility entrypoint。

核心翻译改动：
- `crates/c2r-translator/src/typed_ir.rs`
  - `emit_call_expr()` 现在先对整组实参运行 `validate_bounded_call_args()`，再发射 Rust。
  - 新增一层 nested direct call 实参支持：`outer(inner(value))` 可发射为同形 Rust，只要 outer/inner callee 都是合法 identifier，inner 返回当前支持的 scalar integer，inner args 仍属于无 call 的 bounded arg subset。
  - `outer(inner(third(value)))` 继续 fail closed。
  - `outer(left(value), right(value))` 继续 fail closed，避免在未建模 C sibling argument evaluation order 时错误改写语义。
  - `outer(inner(value) + 1)`、`outer(arr[inner(value)])`、call arg 中 inc/dec、deref、addr-of、null、conditional、array literal、unsupported expr 仍 fail closed。
- `crates/c2r-translator/src/clang_frontend.rs`
  - `call_expr_skeleton_from_ast()` 先构建全部 arg skeleton，再用 `bounded_call_args_rejection_reason()` 做整组参数门禁。
  - direct callee 证明仍要求 clang `referencedDecl.kind=FunctionDecl`；function pointer / complex callee 不因 nested call 支持而放开。
  - nested direct call result 只接受 clang type skeleton 中的 supported integer scalar；void/pointer/array/unsupported result 仍 fail closed。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 把旧的 `typed_ir_rejects_nested_direct_call_arguments` 改成正例 `typed_ir_emits_nested_direct_call_argument`。
  - 新增 `typed_ir_rejects_deeper_nested_direct_call_arguments`。
  - 新增 `typed_ir_rejects_multiple_nested_direct_call_arguments`。
  - 新增真实 clang AST opt-in smoke `clang_ast_dump_lowers_nested_direct_call_expr_when_enabled`。
  - 新增真实 clang AST fail-closed smoke `clang_ast_dump_rejects_multiple_nested_direct_call_args_when_enabled`。

比赛环境配置改动：
- `config/competition-env/toolchain-check.sh`
- `validation/environment-profiles/huawei-competition-ubuntu-24.04/toolchain-check.sh`
  - 新增 profile 文件镜像源检查：APT、pip、npm、Cargo registry 必须包含用户指定的 Huawei mirror。
  - 两个入口继续保持相同逻辑；区别仅在 `env.sh` 的 profile path 和 README 入口说明。

文档同步：
- `docs/c2rust-migration-agent/core-translation-architecture.md`
- `docs/c2rust-migration-agent/core-translation-architecture.en.md`
- `codex/translator-strengthening-analysis.md`
- `codex/translator-strengthening-analysis.en.md`
  - nested direct call 从“下一刀/完全不支持”更新为“一层单个 direct call argument 已支持”。
  - 文档明确保留 deeper nesting、多个 sibling nested call、binary/index/cast 内 nested call、condition tree call、function pointer callee、inc/dec/deref 参数的 fail-closed 边界。

红灯已观察：
```powershell
cargo test --features "typed-ir clang-frontend" typed_ir_emits_nested_direct_call_argument --test bounded_translation
```

旧实现失败于：
- `stmt[0].return expr call arg[0] nested call expressions are outside the bounded call subset`

focused 验证：
```powershell
cargo test --features "typed-ir clang-frontend" nested --test bounded_translation
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --features "typed-ir clang-frontend" nested_direct_call --test bounded_translation -- --nocapture
```

focused 结果：
- `nested` filter：13 passed。
- real clang `nested_direct_call` filter：5 passed，0 skipped，包括 typed IR 正负例和真实 clang AST 正负例。

完整验证：
```powershell
python -m json.tool config\competition-env\environment.json > $null
python -m json.tool validation\environment-profiles\huawei-competition-ubuntu-24.04\environment.json > $null
python -m json.tool validation\l3-template\config-profile.example.json > $null
bash -n config/competition-env/env.sh; bash -n config/competition-env/toolchain-check.sh
bash -n validation/environment-profiles/huawei-competition-ubuntu-24.04/env.sh; bash -n validation/environment-profiles/huawei-competition-ubuntu-24.04/toolchain-check.sh
cargo fmt -- --check
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --features "clang-frontend typed-ir clang-lowering-report" -- --nocapture
git diff --check
```

完整验证结果：
- config/profile JSON 校验通过。
- shell syntax 校验通过。
- `cargo fmt --check` 通过。
- 完整 translator gate 通过：`src/lib.rs` 48 passed，`bounded_translation.rs` 349 passed，doc-tests 0 passed。
- `git diff --check` exit 0，仅报告 Windows LF/CRLF 提示。

边界：
- 可以说：generic typed IR 现在支持一层单个 nested direct call argument，例如 `return outer(inner(value));`，并且 direct typed IR、真实 clang AST 和 rustc snippet smoke 均已覆盖。
- 可以说：这个支持仍是 candidate generation，不是外部 callee semantic acceptance；external callee 仍需要现有 call evidence/signature/source binding 以及完整 validation gates。
- 不应说：已支持 function pointer call、任意 nested call、多个 sibling nested call、condition 中 call、复杂 call side effect、call argument 中 inc/dec/deref、full C argument evaluation semantics 或 semantic acceptance。
- 后续建议：下一刀优先 standalone typed clang inc/dec statement；并行推进 struct/alias memory model OpenSpec + pointer/slice evidence schema，避免 mutable pointer output write 误扩张成完整 C pointer ownership 模型。该 schema/effect graph 对齐已由第 120 和第 122 节推进完成，完整 pointer ownership model 仍未完成。

English mirror summary:

- Added one-level single nested direct call argument support to the generic typed IR emitter.
- `outer(inner(value))` now lowers through direct typed IR and real clang AST when both callees are direct identifiers and the nested result is a supported integer scalar.
- Deeper nesting, multiple sibling nested calls, nested calls hidden in binary/index/cast operands, function-pointer callees, calls in conditions, and side-effect arguments still fail closed.
- Strengthened competition profile self-check scripts to verify the checked-in APT, pip, npm, and Cargo Huawei mirror configuration files.
- Full translator gate passes with real clang enabled: 48 lib tests, 349 bounded translation tests, and 0 doc-tests.

## 119. 2026-06-27 standalone typed clang inc/dec statements

本轮继续按多智能体推进 `c2r-translator` 通用语法面，完成第 118 节建议的 standalone typed clang inc/dec statement 快刀。三个只读子智能体分别给出结论：
- inc/dec 代码路径：当前普通函数体 `UnaryOperator` statement 会在 `stmt_skeleton_from_ast()` 落到 `Unsupported`；已有 `ForStmt` step helper 可把 inc/dec 降成 `Assign`，应抽成 statement 通用 helper。
- 文档同步：需要更新 `core-translation-architecture` 中英文、README 中英文、translator-strengthening-analysis 中英文，并在 CONTEXT 新章节说明第 118 节的下一刀建议已完成。
- alias/memory model：应单独做 `add-struct-alias-memory-model-evidence` OpenSpec，不应和 inc/dec 语法切片混在一起；当前 pointer graph / slice spec / manifest schema 与 validator 的 alias gate 字段仍不一致。

核心翻译改动：
- `crates/c2r-translator/src/clang_frontend.rs`
  - `stmt_skeleton_from_ast()` 新增普通 `UnaryOperator` statement 分支。
  - 原 `inc_dec_for_step_skeleton_from_ast()` 改为 wrapper，复用新的 `inc_dec_stmt_skeleton_from_ast(stmt, context)`。
  - standalone `value++` / `++value` / `value--` / `--value` 在表达式值被丢弃的 statement 位置会 lowering 成 `ClangStmtSkeleton::Assign`，再进入现有 typed IR `IrStmt::Assign`。
  - 生成形式保持与 `ForStmt` step 一致：`value = value + 1` 或 `value = value - 1`，由 typed IR emitter 发射为 Rust assignment。
  - 仍只支持简单整数变量 target，且 target type 与 inc/dec expression type 必须匹配。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增真实 clang AST opt-in smoke `clang_ast_dump_emits_standalone_inc_dec_statements_when_enabled`。
  - 测试 C 源：`int standalone_inc_dec(int value) { value++; ++value; value--; --value; return value; }`。
  - 断言真实 AST lowering 后是 4 条 `IrStmt::Assign` + `Return`，Rust draft 含 2 条 `value = (value + 1i32);` 和 2 条 `value = (value - 1i32);`，并通过 rustc snippet smoke。
- `crates/c2r-translator/src/clang_frontend.rs` 单元测试
  - 新增 `stmt_skeleton_from_ast_accepts_inc_dec_statement_as_assignment`，覆盖 postfix increment、prefix increment、postfix decrement、prefix decrement 四种 standalone statement。

保留的 fail-closed 边界：
- `return ++value;`、`helper(++value)`、`*++p` 仍在真实 clang AST 层 fail closed。
- `if (value++)` 仍会 lower 成 IR 但在 scalar emitter 条件位置 fail closed。
- `++*p`、`++p`、array/field target、pointer target、缺 `isPostfix` 元数据、非整数 target、target/type mismatch 继续 fail closed。
- 这不是通用 `IrExpr::IncDec` emitter，也不表示 value-position inc/dec、condition/call argument/return 中 inc/dec、完整 C 自增表达式值语义或 semantic acceptance 已支持。

文档同步：
- `docs/c2rust-migration-agent/core-translation-architecture.md`
- `docs/c2rust-migration-agent/core-translation-architecture.en.md`
- `docs/c2rust-migration-agent/README.md`
- `docs/c2rust-migration-agent/README.en.md`
- `codex/translator-strengthening-analysis.md`
- `codex/translator-strengthening-analysis.en.md`
  - standalone inc/dec statement 从“后续切口/不支持”更新为“value-discarded statement 已支持”。
  - 文档明确保留 value-position、condition/call argument/return、复杂 target、pointer/array/field target 和完整语义的 fail-closed 边界。

红灯已观察：
```powershell
cargo test --features "typed-ir clang-frontend" stmt_skeleton_from_ast_accepts_inc_dec_statement_as_assignment -- --nocapture
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --features "typed-ir clang-frontend" clang_ast_dump_emits_standalone_inc_dec_statements_when_enabled --test bounded_translation -- --nocapture
```

旧实现失败于：
- 单元层：`postfix increment: expected assignment statement, got Unsupported { reason: "UnaryOperator opcode ++ is outside the current clang lowering skeleton" }`
- 真实 clang AST 层：`unsupported_clang_stmt: UnaryOperator opcode ++ is outside the current clang lowering skeleton`

focused 验证：
```powershell
cargo test --features "typed-ir clang-frontend" stmt_skeleton_from_ast_accepts_inc_dec_statement_as_assignment -- --nocapture
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --features "typed-ir clang-frontend" clang_ast_dump_emits_standalone_inc_dec_statements_when_enabled --test bounded_translation -- --nocapture
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --features "typed-ir clang-frontend" "prefix_increment" --test bounded_translation -- --nocapture
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --features "typed-ir clang-frontend" "postfix_increment_if" --test bounded_translation -- --nocapture
```

focused 结果：
- 单元 inc/dec statement：1 passed。
- 真实 clang standalone inc/dec statement：1 passed。
- `prefix_increment` regression filter：4 passed，覆盖 for-step 正例和 return/call/deref 负例。
- `postfix_increment_if` regression filter：1 passed，condition 位置仍 fail closed。

后续建议：
- 下一刀优先做 `add-struct-alias-memory-model-evidence`，把 pointer graph、slice spec、auto translation plan、evidence manifest、validator 和测试中的 `alias_contract` / `alias_risks` / `safe_boundary_preconditions` / ownership / effect graph 字段对齐。
- 其次才考虑更宽 `switch` / `goto` 或 struct/field access；不要在 alias gate 未固化前扩大 pointer/struct emitter。

English mirror summary:

- Added standalone value-discarded clang inc/dec statement lowering.
- `value++`, `++value`, `value--`, and `--value` now lower to assignment candidates when used as ordinary statements.
- The implementation reuses the existing `ForStmt` step inc/dec-to-Assign path through a shared helper.
- Value-position inc/dec, inc/dec in conditions/call arguments/returns, complex targets, pointer/array/field targets, and full C increment-expression semantics still fail closed.
- Focused tests pass for the new unit path, real clang AST smoke, and existing negative regressions.

## 120. 2026-06-27 struct alias memory-model evidence templates

本轮继续按多智能体推进 `add-struct-alias-memory-model-evidence`。三个只读子智能体分别审计了 pointer graph 模板、slice/plan/manifest 模板、validator 与测试；共同结论是：真实 `auto_migrate.py` 和 validator 已经在使用 `alias_contract`、`alias_risks`、`safe_boundary_preconditions`、`translation_summary.alias_gate`、`claim_boundary.alias_gate`，但通用 schema/example/docs 没有完整表达这些字段。

核心改动：

- 新增 `validation/tools/test_template_schema_contracts.py`，用 schema/example 自检固定 pointer graph、slice spec、auto-translation plan、L3 manifest 的 alias/memory-model 字段契约。
- `validation/pointer-graph-template/pointer-graph.schema.json` 新增 `alias_contract`、`alias_risks`、`safe_boundary_preconditions`、`effect_graph`、`pointer_decisions`，并给 `pointer_nodes[]` 增加 `read_effects` / `write_effects` / length/boundary 字段。
- `validation/pointer-graph-template/pointer-graph.example.json` 补 alias gate、effect graph 和 per-node read/write effect 示例。
- `validation/slice-spec-template/slice-spec.schema.json` 新增 `c_boundary.pointer_contract` 和 `memory_model`，覆盖 input buffers、output pointers、inout pointers、length companions、read/write effects、aliasing proof、read-read alias allowance 和 noalias-required pairs。
- `validation/slice-spec-template/slice-spec.example.json` 补 pointer contract 与 memory model 示例。
- `validation/auto-translation-template/auto-translation-plan.schema.json` 和 example 新增 `translation_summary.alias_gate`。
- `validation/l3-template/evidence-manifest.schema.json` 和 example 新增 `claim_boundary.alias_gate`，并修复 example 缺失的 `c2rust_baseline`、`route_decision`、`validation_profile` required refs。
- pointer graph、slice spec、auto translation、L3 template 的 README/checklist 已补中英文说明，强调 FlashDB 只是用例，alias gate 是通用 pointer/struct/external-state 风险门禁，不是 whole-program alias proof。
- 新增 OpenSpec change：`openspec/changes/add-struct-alias-memory-model-evidence/`。

兼容策略：

- 本次 schema 先保持 additive，不强制迁移所有历史 evidence。
- 新模板能表达 alias/memory/effect 字段；运行时 validator 继续对新生成的 alias-sensitive evidence fail-closed。
- `effect_graph` 已进入模板和 example，但本节暂不要求所有现有 generated evidence 必填；第 122 节已让 `auto_migrate.py` 生成 v2 `effect_graph`，并对 alias-sensitive v2 evidence 收紧条件 required。

验证：

```powershell
python -m unittest validation.tools.test_template_schema_contracts
python -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_alias_sensitive_read_write_pointer_gate_flows_through_auto_migrate validation.tools.test_auto_migrate.AutoMigrateTests.test_output_only_pointer_write_does_not_trigger_input_output_alias_risk validation.tools.test_auto_migrate.AutoMigrateTests.test_cache_identity_tracks_alias_gate_inputs
python -m unittest validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_rejects_read_write_pointer_graph_missing_alias_gate_fields validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_rejects_missing_alias_gate_in_manifest_and_final_verification validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_rejects_empty_alias_risk_and_noalias_precondition_for_unknown_alias
python -m json.tool validation/pointer-graph-template/pointer-graph.schema.json > $null
python -m json.tool validation/pointer-graph-template/pointer-graph.example.json > $null
python -m json.tool validation/slice-spec-template/slice-spec.schema.json > $null
python -m json.tool validation/slice-spec-template/slice-spec.example.json > $null
python -m json.tool validation/auto-translation-template/auto-translation-plan.schema.json > $null
python -m json.tool validation/auto-translation-template/auto-translation-plan.example.json > $null
python -m json.tool validation/l3-template/evidence-manifest.schema.json > $null
python -m json.tool validation/l3-template/evidence-manifest.example.json > $null
openspec validate add-struct-alias-memory-model-evidence --strict
openspec validate --all --strict
git diff --check
```

结果：

- `test_template_schema_contracts`: 3 passed。
- alias auto-migrate focused tests: 3 passed。
- alias validator focused tests: 3 passed。
- 8 个修改 JSON 文件均可 parse。
- OpenSpec change valid。
- OpenSpec 全量 strict 校验 38 passed, 0 failed。
- `git diff --check` exit 0，仅有 Windows LF/CRLF 提示。

下一步建议：

- 第 122 节已让 `auto_migrate.py` 生成真实 `effect_graph`，并把 alias-sensitive pointer graph v2 从“能表达字段”收紧到“条件 required”。
- 后续再扩 struct/field access emitter；不要把当前 effect graph / alias gate 误读成完整 C pointer ownership 模型。

English mirror summary:

- Added the reusable alias/memory-model evidence contract for pointer-bearing and struct-ready bounded translation slices.
- Pointer graph templates now expose alias contract, alias risks, safe boundary preconditions, effect graph, pointer decisions, and per-node read/write effects.
- Slice spec templates now expose `c_boundary.pointer_contract` and `memory_model`.
- Auto-translation plan and L3 manifest templates now expose alias-gate summaries.
- Docs/checklists are bilingual and clarify that FlashDB is only a use case; the gate is generic evidence, not a whole-program alias proof.
- Focused schema, auto-migrate, validator, JSON, OpenSpec, and whitespace checks pass.

## 121. 2026-06-27 competition environment binding for auto translation

本轮按用户补充的比赛环境配置做适配收口。仓库已有独立入口 `config/competition-env/`，但自动翻译 evidence 还没有把该 profile 作为一等 cache/provenance 输入；机器可读 `environment.json` 里 C++ 编译器字段也写成了 `gpp`，与真实命令和文档的 `g++` 不一致。

核心改动：

- 新增 `validation/tools/test_competition_environment_profile.py`，锁定比赛环境基线：
  - Ubuntu 24.04.4 LTS / Noble、kernel `5.10.0-182.0.0.95.r194_123.hce2.x86_64`。
  - Huawei APT/PyPI/npm/Cargo mirror。
  - Python 3.12.3、pip 24.0、Node v24.13.0、npm 11.6.2、OpenJDK 21.0.10 (`bisheng_jdk_enterprise`)、Maven 3.9.11、`MAVEN_HOME=/usr/local/maven3`、Rust/Cargo 1.96.0、gcc/g++ 13.3.0、GNU Make 4.3。
  - Go 未安装、CMake 未找到。
  - `config/competition-env/` 与兼容目录 `validation/environment-profiles/huawei-competition-ubuntu-24.04/` 的关键配置文件保持 SHA256 同步。
- `config/competition-env/environment.json` 和兼容拷贝把 `toolchain.gpp` 修为 `toolchain["g++"]`。
- `auto_migrate.py` 新增 `competition_environment_identity()`，默认读取 `config/competition-env/environment.json`，把 `profile_id`、相对路径和文件 SHA256 写入：
  - `l3-<slice>-validation-profile.json` 的 `competition_environment`。
  - `l3-<slice>-auto-cache-metadata.json` 的 `competition_environment_identity`。
  - `cache_input_fields`，使比赛 profile 变化自动触发候选/CFG/pointer graph/Rust draft/oracle/diff/unsafe/final/summary 等 artifact 失效。
- `validation/auto-translation-template/validation-profile.schema.json` 显式增加 `competition_environment` schema。
- `validate_auto_translation_evidence.py` 增加条件校验：如果 validation profile 绑定了 `competition_environment`，cache metadata 必须带一致的 `competition_environment_identity`，且该 key 必须在 `cache_input_fields` 中。
- 中英文文档同步：
  - `validation/README.md`
  - `validation/auto-translation-template/README.md`
  - `docs/c2rust-migration-agent/bounded-auto-translation-pipeline.md`
  - `docs/c2rust-migration-agent/bounded-auto-translation-pipeline.en.md`

红灯已观察：

```powershell
python -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_route_baseline_and_validation_profile_evidence_are_emitted
python -m unittest validation.tools.test_competition_environment_profile
python -m unittest validation.tools.test_template_schema_contracts.TemplateSchemaContractTests.test_validation_profile_template_exposes_competition_environment_contract
python -m unittest validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_rejects_cache_missing_competition_environment_identity_when_profile_binds_it
```

旧实现分别失败于：

- `KeyError: 'competition_environment'`
- `KeyError: 'g++'`
- validation profile schema 缺 `competition_environment`
- validator 放过缺失 `competition_environment_identity` 的 cache metadata。

已验证：

```powershell
python -m unittest validation.tools.test_competition_environment_profile validation.tools.test_template_schema_contracts
python -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_route_baseline_and_validation_profile_evidence_are_emitted validation.tools.test_auto_migrate.AutoMigrateTests.test_cache_drift_invalidates_reusable_translation_artifacts validation.tools.test_auto_migrate.AutoMigrateTests.test_cache_identity_tracks_alias_gate_inputs validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_rejects_cache_missing_competition_environment_identity_when_profile_binds_it validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_rejects_cache_missing_route_baseline_profile_identities validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_rejects_cache_route_baseline_profile_identity_sha_drift
python -m json.tool config/competition-env/environment.json > $null
python -m json.tool validation/environment-profiles/huawei-competition-ubuntu-24.04/environment.json > $null
python -m json.tool validation/auto-translation-template/validation-profile.schema.json > $null
python -m unittest validation.tools.test_auto_migrate
python -m unittest validation.tools.test_validate_auto_translation_evidence
```

结果：

- competition environment + template schema tests: 6 passed。
- focused cache/profile/validator tests: 6 passed。
- 3 个 JSON 文件 parse 通过。
- `test_auto_migrate`: 64 passed。
- `test_validate_auto_translation_evidence`: 67 passed。
- 注意：曾并行运行 `test_auto_migrate` 和 `test_validate_auto_translation_evidence`，validator 中 4 个 helper 调 `auto_migrate.py` 出现瞬态 `CalledProcessError`；同一失败测试单独复现通过，随后 validator 全量单独通过。后续宽测试不要并发跑这两个大量启动 `auto_migrate.py` 的 test module。

下一步建议：

- section 120 的 effect graph 主线已在第 122 节完成：`auto_migrate.py` 为新生成 pointer graph 写入 v2 `effect_graph`，validator 对 alias-sensitive v2 evidence 条件必填。
- `validation/tools/run_wave2_l1.py` 后续可加 competition profile guard：默认比赛环境下把 CMake/Go 项目标为 non-default environment required，而不是误当默认 gate。

English mirror summary:

- Bound generated auto-translation validation profiles and cache metadata to the standalone competition environment profile at `config/competition-env/environment.json`.
- Fixed the machine-readable C++ compiler key from `gpp` to `g++` in both the default and compatibility profile copies.
- Added tests for the exact competition baseline and profile-directory synchronization.
- Added schema and validator checks for `competition_environment` and `competition_environment_identity`.
- Updated bilingual docs; section 122 completes the real `effect_graph` generation path for alias-sensitive pointer evidence.
