## 54. 2026-06-26 clang assignment and BitCast lowering

本轮承接第 53 节的真实 blocker：只为 clang AST lowering report 增加最小 assignment
和 `CStyleCastExpr(BitCast)` 支持，让 real-fdb `fdb_calc_crc32` 从
`p = (const uint8_t *)buf;` 推进到 `crc = crc ^ ~0U;` 的表达式层。

核心改动：
- `crates/c2r-translator/src/clang_frontend.rs`
  - `ClangStmtSkeleton` 新增 `Assign { target, value }`。
  - `ClangExprSkeleton` 新增 `Cast { target, expr, implicit }`。
  - `stmt_skeleton_from_ast()` 现在仅把 statement-level `BinaryOperator opcode "="`
    识别为 assignment；其他 statement-level binary op 仍走 unsupported。
  - `assign_stmt_skeleton_from_ast()` 要求 assignment 有且仅有两个 operand。
  - `expr_skeleton_from_ast()` 现在支持 `CStyleCastExpr`，但仅接受
    `castKind == "BitCast"`；`IntegralCast` 等其他 castKind 仍 unsupported。
  - `lower_stmt()` 能把 `Assign` lower 成 `IrStmt::Assign`。
  - `lower_expr()` 能把显式 cast lower 成 `IrExpr::Cast { implicit=false }`。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 `clang_lowering_skeleton_maps_pointer_cast_assignment`，验证 skeleton 层
    `p = (const uint8_t *)buf` 会变成 `IrStmt::Assign` + 显式 `IrExpr::Cast`。
  - 将真实 clang assignment smoke 从只检查 unsupported opcode 改为
    `clang_ast_dump_lowers_assignment_statement_when_enabled`，验证 `crc = crc;` 能 lower。
  - 新增 `clang_ast_dump_lowers_pointer_cast_assignment_when_enabled`，验证真实 clang
    的 `p = (const uint8_t *)buf;` 形状能 lower。
  - 新增 `clang_ast_dump_rejects_non_bitcast_c_style_cast_when_enabled`，确认
    `CStyleCastExpr castKind="IntegralCast"` 仍 fail-closed。

TDD 红绿过程：
- 红灯 1：`clang_lowering_skeleton_maps_pointer_cast_assignment` 先失败在
  `ClangStmtSkeleton::Assign` 和 `ClangExprSkeleton::Cast` 不存在。
- 绿灯 1：新增 `Assign`/`Cast` skeleton、assignment parser、`CStyleCastExpr` parser
  和 lowering 后，skeleton 与真实 clang assignment/cast smoke 均通过。
- 红灯 2：`clang_ast_dump_rejects_non_bitcast_c_style_cast_when_enabled` 先失败，
  因为当前实现会把 `IntegralCast` 错误 lower 为成功。
- 绿灯 2：`CStyleCastExpr` 分支增加 `castKind == "BitCast"` 检查，非 BitCast
  返回 unsupported。

真实 real-fdb 临时 report 推进结果：
- 第 53 节末尾：
  `unsupported_clang_stmt: BinaryOperator opcode = is outside the current clang lowering skeleton`。
- 本轮后：
  `unsupported_clang_expr: BinaryOperator: opcode ^ is outside the current skeleton`。
- 这对应 `fdb_utils.c` 中 `crc = crc ^ ~0U;` 的 RHS 表达式层。

本轮并行只读审查结论：
- Carson：采样真实 `p = (const uint8_t *)buf;` AST，确认形状为
  `BinaryOperator("=") -> DeclRefExpr(p) + CStyleCastExpr(BitCast) -> ImplicitCastExpr -> DeclRefExpr(buf)`。
  同时指出必须检查 `castKind == "BitCast"`，否则会误收 `IntegralCast`。本轮已采纳。
- McClintock：确认当前 lower 出的 `IrStmt::Assign { target: Var(p), value: Cast(target=u8*, expr=Var(buf), implicit=false) }`
  能匹配 `matches_pointer_cast_assignment()`；但完整 `is_crc32_byte_cursor_ir()` gate
  仍要求 5 条固定语句、固定参数名和后续 while/table/bit-op 形状，不能把本轮理解为完整 clang CRC32 通路打通。

已通过命令：
```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_lowering_skeleton_maps_pointer_cast_assignment -- --nocapture
$env:PATH = 'C:\Program Files\LLVM\bin;' + $env:PATH
$env:LIBCLANG_PATH = 'C:\Program Files\LLVM\bin\libclang.dll'
$env:CLANG_PATH = 'C:\Program Files\LLVM\bin\clang.exe'
$env:C2R_RUN_CLANG_AST_TESTS = '1'
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_ast_dump_lowers_assignment_statement_when_enabled -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_ast_dump_lowers_pointer_cast_assignment_when_enabled -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_ast_dump_rejects_non_bitcast_c_style_cast_when_enabled -- --nocapture
cargo fmt --manifest-path crates/c2r-translator/Cargo.toml
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report
python -B validation/tools/auto_migrate.py --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json --out-root <temp> --skip-c-oracle --skip-rust-check --emit-clang-lowering-report
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_run_translator_emit_clang_lowering_report_enables_report_feature validation.tools.test_auto_migrate.AutoMigrateTests.test_real_fdb_calc_crc32_emit_clang_lowering_report_opt_in_writes_temp_artifact validation.tools.test_auto_migrate.AutoMigrateTests.test_cache_identity_records_emit_clang_lowering_report_opt_in
```

完整结果：
- focused assignment/cast tests：均 `1 passed`。
- `--features clang-lowering-report` translator crate：`60 passed`。
- focused Python opt-in tests：`Ran 3 tests ... OK`。
- real-fdb 临时 out-root report：`status=unsupported`，
  `errors[0].kind=unsupported_clang_expr`，
  `errors[0].message="BinaryOperator: opcode ^ is outside the current skeleton"`。

当前核心翻译功能状态：
- clang AST lowering 已能跨过 real-fdb 的局部声明和 `p = (const uint8_t *)buf;` assignment。
- 当前真实 blocker 是 `crc = crc ^ ~0U;` 的 RHS：`BinaryOperator opcode "^"`。
- `~0U` 的 `UnaryOperator`、`^`/`&`/`>>`、`while(size--)`、`*p++`、`crc32_table[...]`
  仍未纳入 clang AST lowering subset。
- 完整 CRC32 Rust 生成仍主要来自字符串 recognizer 构造的 hard-coded typed IR，
  不是完整 clang AST lowering 已能驱动 emitter。

下一步建议：
1. 为 `crc = crc ^ ~0U;` 做最小表达式 lowering：`BinaryOperator("^")` 和
   `UnaryOperator("~")` + unsigned zero literal。
2. 补对应 fail-closed 负例，避免一次性放开其他 cast/位运算/复杂表达式。
3. 继续用 real-fdb 临时 out-root report 验证 blocker 推进，下一层预期是
   `WhileStmt` 或 loop condition 的 postfix decrement。

## 55. 2026-06-26 clang bitxor/bitnot expression lowering

本轮承接第 54 节的真实 blocker：只为 clang AST lowering report 增加最小
`crc = crc ^ ~0U;` 表达式支持，并补一个轻量 `ParenExpr` 公差层；不改通用 typed IR
emitter。

核心改动：
- `crates/c2r-translator/src/clang_frontend.rs`
  - `ClangExprSkeleton` 新增 `Unary { op, operand, ty }`。
  - `ClangBinaryOperator` 新增 `BitXor`，映射 clang `BinaryOperator opcode "^"`。
  - 新增 `ClangUnaryOperator::BitNot`，映射 clang `UnaryOperator opcode "~"`。
  - `expr_skeleton_from_ast()` 现在把 `ParenExpr` 和 `ImplicitCastExpr` 一样透明下钻。
  - `lower_expr()` 现在能 lower `Unary` 到 `IrExpr::Unary`。
  - `lower_binary_operator()` / `lower_unary_operator()` 分别映射到
    `IrBinOp::BitXor` / `IrUnOp::BitNot`。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 `clang_lowering_skeleton_maps_bitxor_bitnot_assignment`。
  - 新增真实 clang smoke：
    `clang_ast_dump_lowers_bitxor_bitnot_assignment_when_enabled`。
  - 新增真实 clang smoke：
    `clang_ast_dump_lowers_parenthesized_bitxor_bitnot_assignment_when_enabled`。

TDD 红绿过程：
- 红灯 1：`clang_lowering_skeleton_maps_bitxor_bitnot_assignment` 先失败在
  `ClangUnaryOperator`、`ClangBinaryOperator::BitXor`、`ClangExprSkeleton::Unary`
  不存在。
- 绿灯 1：补最小 skeleton 和 lower 映射后，skeleton 与真实 clang `crc = crc ^ ~0U;`
  smoke 均通过。
- 红灯 2：`clang_ast_dump_lowers_parenthesized_bitxor_bitnot_assignment_when_enabled`
  先失败为 `unsupported_clang_expr: ParenExpr ... outside ...`。
- 绿灯 2：`ParenExpr` 在 `expr_skeleton_from_ast()` 中透明下钻后，该测试通过。

真实 real-fdb 临时 report 推进结果：
- 第 54 节末尾：
  `unsupported_clang_expr: BinaryOperator: opcode ^ is outside the current skeleton`。
- 本轮后：
  `unsupported_clang_stmt: WhileStmt is outside the current clang lowering skeleton`。
- 这对应 `fdb_utils.c` 中已经跨过 `crc = crc ^ ~0U;`，下一层进入循环语句。

本轮并行只读审查结论：
- Russell：真实 clang AST 中 `crc ^ ~0U` 的 RHS 是
  `BinaryOperator("^") -> ImplicitCastExpr(DeclRefExpr crc) + UnaryOperator("~") -> IntegerLiteral("0")`；
  `0U` 后缀不作为 literal spelling 保留，只能从 `type.qualType="unsigned int"` 看出；
  括号版本会多一层 `ParenExpr`。本轮已支持这些最小形状。
- Nash：typed IR 已有 `IrExpr::Binary` / `IrExpr::Unary`、`IrBinOp::BitXor`、
  `IrUnOp::BitNot`，因此本轮不需要动 emitter；当前 emitter 仍只是 CRC32 byte cursor
  特例，不是通用 typed IR -> Rust emitter。

已通过命令：
```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_lowering_skeleton_maps_bitxor_bitnot_assignment -- --nocapture
$env:PATH = 'C:\Program Files\LLVM\bin;' + $env:PATH
$env:LIBCLANG_PATH = 'C:\Program Files\LLVM\bin\libclang.dll'
$env:CLANG_PATH = 'C:\Program Files\LLVM\bin\clang.exe'
$env:C2R_RUN_CLANG_AST_TESTS = '1'
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_ast_dump_lowers_bitxor_bitnot_assignment_when_enabled -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_ast_dump_lowers_parenthesized_bitxor_bitnot_assignment_when_enabled -- --nocapture
cargo fmt --manifest-path crates/c2r-translator/Cargo.toml
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_run_translator_emit_clang_lowering_report_enables_report_feature validation.tools.test_auto_migrate.AutoMigrateTests.test_real_fdb_calc_crc32_emit_clang_lowering_report_opt_in_writes_temp_artifact validation.tools.test_auto_migrate.AutoMigrateTests.test_cache_identity_records_emit_clang_lowering_report_opt_in
python -B validation/tools/auto_migrate.py --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json --out-root <temp> --skip-c-oracle --skip-rust-check --emit-clang-lowering-report
```

完整结果：
- focused bitxor/bitnot skeleton test：`1 passed`。
- 两条真实 clang bitxor/bitnot smoke：均 `1 passed`。
- `--features clang-lowering-report` translator crate：`64 passed`。
- focused Python opt-in tests：`Ran 3 tests ... OK`。
- real-fdb 临时 out-root report：`status=unsupported`，
  `errors[0].kind=unsupported_clang_stmt`，
  `errors[0].message="WhileStmt is outside the current clang lowering skeleton"`。

当前核心翻译功能状态：
- clang AST lowering 已能跨过 real-fdb 的局部声明、指针 cast assignment、
  `crc = crc ^ ~0U;`。
- 当前真实 blocker 是 `WhileStmt`，下一步要面对 `while (size--)` 的 condition、
  postfix decrement、循环体中的 `*p++`、`& 0xff`、`>> 8`、table lookup 和后续 `^`。
- 完整 CRC32 Rust 生成仍不是由真实 clang AST lowering 直接驱动；通用 recursive emitter
  仍可后置。

下一步建议：
1. 为 `WhileStmt` 写最小 skeleton/真实 clang smoke，但只支持一个 condition + compound body
   的外壳，先把 report 推进到 condition 内的 `UnaryOperator("--")`。
2. 继续把 `ParenExpr`/`ImplicitCastExpr` 当作透明包装处理，避免真实 clang AST 的无害包装
   让 report 提前 fail。
3. 暂不扩展通用 emitter，等 CRC32 typed IR 形状能从 clang lowering 串起来后再决定。

## 56. 2026-06-26 clang WhileStmt outer-shell lowering

本轮承接第 55 节的真实 blocker：只为 clang AST lowering report 增加最小 `WhileStmt`
外壳支持，把 real-fdb `fdb_calc_crc32` 从 `WhileStmt` 推进到 condition 内的
postfix decrement；不支持 `size--` 本身，也不扩展 emitter。

核心改动：
- `crates/c2r-translator/src/clang_frontend.rs`
  - `ClangStmtSkeleton` 新增 `While { condition, body }`。
  - `function_skeleton_from_ast()` 现在复用 `compound_body_skeleton_from_ast()` 展开
    顶层 `CompoundStmt`。
  - 新增 `compound_body_skeleton_from_ast()`，把 `CompoundStmt.inner` 递归映射为
    `Vec<ClangStmtSkeleton>`。
  - `stmt_skeleton_from_ast()` 现在识别 `WhileStmt`。
  - 新增 `while_stmt_skeleton_from_ast()`，要求 `WhileStmt` 恰好有 condition/body 两个
    child，且 body 必须是 `CompoundStmt`。
  - `lower_stmt()` 现在能把 skeleton while lower 成 `IrStmt::While`。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 `clang_lowering_skeleton_maps_simple_while_statement`。
  - 新增真实 clang smoke：
    `clang_ast_dump_lowers_simple_while_statement_when_enabled`。
  - 新增真实 clang fail-closed smoke：
    `clang_ast_dump_reports_postfix_decrement_while_condition_when_enabled`。

TDD 红绿过程：
- 红灯 1：`clang_lowering_skeleton_maps_simple_while_statement` 先失败在
  `ClangStmtSkeleton::While` 不存在。
- 绿灯 1：补 `While` skeleton、`WhileStmt` parser、`CompoundStmt` body 展开和
  `IrStmt::While` lowering 后，skeleton 与真实 clang simple while smoke 均通过。
- `clang_ast_dump_reports_postfix_decrement_while_condition_when_enabled` 确认
  `while (size--)` 仍 fail-closed 到 `unsupported_clang_expr`，message 包含
  `UnaryOperator: opcode --`。

真实 real-fdb 临时 report 推进结果：
- 第 55 节末尾：
  `unsupported_clang_stmt: WhileStmt is outside the current clang lowering skeleton`。
- 本轮后：
  `unsupported_clang_expr: UnaryOperator: opcode -- is outside the current skeleton`。
- 这对应 `while (size--)` 的 condition 层。

本轮并行只读审查结论：
- Ohm：真实 `fdb_calc_crc32` 顶层顺序仍为
  `DeclStmt -> BinaryOperator("=") -> BinaryOperator("=") -> WhileStmt -> ReturnStmt`；
  `WhileStmt.inner[0]` 是 `UnaryOperator opcode="--" isPostfix=true`，`inner[1]`
  是 `CompoundStmt`；循环体第一层是 assignment。
- Arendt：typed IR 已有 `IrStmt::While { condition, body }`，不需要新增 compound IR；
  当前 emitter 仍不是通用 while emitter；`while(size--)`、无大括号 body、`break`/`continue`
  等仍应 fail-closed。本轮保留 body 必须是 `CompoundStmt` 的窄边界。

已通过命令：
```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_lowering_skeleton_maps_simple_while_statement -- --nocapture
$env:PATH = 'C:\Program Files\LLVM\bin;' + $env:PATH
$env:LIBCLANG_PATH = 'C:\Program Files\LLVM\bin\libclang.dll'
$env:CLANG_PATH = 'C:\Program Files\LLVM\bin\clang.exe'
$env:C2R_RUN_CLANG_AST_TESTS = '1'
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_ast_dump_lowers_simple_while_statement_when_enabled -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_ast_dump_reports_postfix_decrement_while_condition_when_enabled -- --nocapture
cargo fmt --manifest-path crates/c2r-translator/Cargo.toml
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_run_translator_emit_clang_lowering_report_enables_report_feature validation.tools.test_auto_migrate.AutoMigrateTests.test_real_fdb_calc_crc32_emit_clang_lowering_report_opt_in_writes_temp_artifact validation.tools.test_auto_migrate.AutoMigrateTests.test_cache_identity_records_emit_clang_lowering_report_opt_in
python -B validation/tools/auto_migrate.py --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json --out-root <temp> --skip-c-oracle --skip-rust-check --emit-clang-lowering-report
```

完整结果：
- focused while skeleton test：`1 passed`。
- 两条真实 clang while smoke：均 `1 passed`。
- `--features clang-lowering-report` translator crate：`67 passed`。
- focused Python opt-in tests：`Ran 3 tests ... OK`。
- real-fdb 临时 out-root report：`status=unsupported`，
  `errors[0].kind=unsupported_clang_expr`，
  `errors[0].message="UnaryOperator: opcode -- is outside the current skeleton"`。

当前核心翻译功能状态：
- clang AST lowering 已能跨过 real-fdb 的局部声明、指针 cast assignment、
  `crc = crc ^ ~0U;` 和 `WhileStmt` 外壳。
- 当前真实 blocker 是 `while (size--)` 的 postfix decrement condition。
- 真实循环体后续仍有 `*p++`、`& 0xff`、`>> 8`、`crc32_table[...]`、table lookup 和
  后续 `^` 等缺口。
- 完整 CRC32 Rust 生成仍不是由真实 clang AST lowering 直接驱动。

下一步建议：
1. 为 `UnaryOperator("--") isPostfix=true` 写最小 lowering，映射到现有
   `IrExpr::IncDec { op: Dec, prefix: false }`。
2. 同时补负例：prefix decrement 或 unsupported unary opcode 不应被误收。
3. 继续用 real-fdb 临时 report 验证 blocker 推进；预期下一层进入循环体里的
   table/index/deref 表达式。

## 57. 2026-06-26 clang postfix decrement lowering

本轮承接第 56 节的真实 blocker：只为 clang AST lowering report 增加最小
`UnaryOperator("--") isPostfix=true` 支持，让 `while (size--)` 的 condition lower
成现有 typed IR `IrExpr::IncDec`；prefix `--size` 和 `++` 仍 fail-closed。

核心改动：
- `crates/c2r-translator/src/clang_frontend.rs`
  - `ClangExprSkeleton` 新增 `IncDec { target, op, prefix, ty }`。
  - 新增 `ClangIncDecOperator::Dec`。
  - `expr_skeleton_from_ast()` 在 `UnaryOperator opcode "--"` 且 `isPostfix == true`
    时生成 `ClangExprSkeleton::IncDec { prefix=false }`。
  - `UnaryOperator opcode "--"` 但不是 postfix 时返回
    `unsupported_clang_expr: prefix opcode -- ...`。
  - `lower_expr()` 能把 clang inc/dec lower 成 `IrExpr::IncDec`。
  - 新增 `lower_inc_dec_operator()`，当前只映射 `Dec -> IrIncDecOp::Dec`。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 `clang_lowering_skeleton_maps_postfix_decrement_condition`。
  - 将真实 clang smoke 改为
    `clang_ast_dump_lowers_postfix_decrement_while_condition_when_enabled`。
  - 新增真实 clang 负例：
    `clang_ast_dump_rejects_prefix_decrement_while_condition_when_enabled`。

TDD 红绿过程：
- 红灯 1：`clang_lowering_skeleton_maps_postfix_decrement_condition` 先失败在
  `ClangIncDecOperator` 和 `ClangExprSkeleton::IncDec` 不存在。
- 绿灯 1：补专用 IncDec skeleton、postfix `--` parser 和 `IrExpr::IncDec` lowering 后，
  skeleton 与真实 clang postfix decrement smoke 均通过。
- 负例：`while (--size)` 继续返回 unsupported，message 包含 `prefix opcode --`。

真实 real-fdb 临时 report 推进结果：
- 第 56 节末尾：
  `unsupported_clang_expr: UnaryOperator: opcode -- is outside the current skeleton`。
- 本轮后：
  `unsupported_clang_expr: ArraySubscriptExpr: ArraySubscriptExpr is outside the current clang lowering skeleton`。
- 这说明已经跨过 `while (size--)` condition，进入循环体中
  `crc32_tab[(crc ^ *p++) & 0xff]` 的 table/index 表达式层。

本轮并行只读审查结论：
- Hegel：真实 clang AST 用 `UnaryOperator opcode="--"` 表示 prefix/postfix decrement，
  必须看 `isPostfix`；`while(size--)` 是 `isPostfix=true`，
  `while(--size)` 是 `isPostfix=false`。`*p++` 后续形状是
  `UnaryOperator("*") -> UnaryOperator("++" isPostfix=true) -> DeclRefExpr(p)`。
- Plato：`IrExpr::IncDec { target, op, prefix, ty }` 已能表达 `size--`；
  应使用专用 clang IncDec skeleton，不应复用纯 `Unary(BitNot)`；
  `++`、复杂 lvalue、`return value++`、`helper(value++)` 仍应 fail-closed。

已通过命令：
```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_lowering_skeleton_maps_postfix_decrement_condition -- --nocapture
$env:PATH = 'C:\Program Files\LLVM\bin;' + $env:PATH
$env:LIBCLANG_PATH = 'C:\Program Files\LLVM\bin\libclang.dll'
$env:CLANG_PATH = 'C:\Program Files\LLVM\bin\clang.exe'
$env:C2R_RUN_CLANG_AST_TESTS = '1'
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_ast_dump_lowers_postfix_decrement_while_condition_when_enabled -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_ast_dump_rejects_prefix_decrement_while_condition_when_enabled -- --nocapture
cargo fmt --manifest-path crates/c2r-translator/Cargo.toml
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_run_translator_emit_clang_lowering_report_enables_report_feature validation.tools.test_auto_migrate.AutoMigrateTests.test_real_fdb_calc_crc32_emit_clang_lowering_report_opt_in_writes_temp_artifact validation.tools.test_auto_migrate.AutoMigrateTests.test_cache_identity_records_emit_clang_lowering_report_opt_in
python -B validation/tools/auto_migrate.py --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json --out-root <temp> --skip-c-oracle --skip-rust-check --emit-clang-lowering-report
```

完整结果：
- focused postfix decrement skeleton test：`1 passed`。
- 真实 clang postfix decrement smoke：`1 passed`。
- 真实 clang prefix decrement 负例：`1 passed`。
- `--features clang-lowering-report` translator crate：`69 passed`。
- focused Python opt-in tests：`Ran 3 tests ... OK`。
- real-fdb 临时 out-root report：`status=unsupported`，
  `errors[0].kind=unsupported_clang_expr`，
  `errors[0].message="ArraySubscriptExpr: ArraySubscriptExpr is outside the current clang lowering skeleton"`。

当前核心翻译功能状态：
- clang AST lowering 已能跨过 real-fdb 的局部声明、指针 cast assignment、
  `crc = crc ^ ~0U;`、`WhileStmt` 外壳和 `while(size--)` condition。
- 当前真实 blocker 是循环体里的 `ArraySubscriptExpr`，来自
  `crc32_tab[(crc ^ *p++) & 0xff]`。
- 后续仍需分层处理 `ArraySubscriptExpr`、`BinaryOperator("&")`、`UnaryOperator("*")`、
  postfix `++`、`BinaryOperator(">>")` 以及 table lookup。
- 完整 CRC32 Rust 生成仍不是由真实 clang AST lowering 直接驱动。

下一步建议：
1. 先采样/测试 `crc32_tab[(crc ^ *p++) & 0xff]` 的真实 AST，决定先补
   `ArraySubscriptExpr` 外壳还是先补内部 `&`/`*p++`。
2. 如果继续按 report blocker 顺序，下一步应先为 `ArraySubscriptExpr` 写最小 skeleton，
   并让内部表达式继续 fail-closed 到 `BinaryOperator("&")` 或 `UnaryOperator("*")`。
3. 不要同时打开 `++`、deref、index、`&`、`>>` 全套；继续每次只推进一个真实 blocker。

## 58. 2026-06-26 clang ArraySubscriptExpr and array type lowering

本轮承接第 57 节的真实 blocker：先为 clang AST lowering report 增加最小
`ArraySubscriptExpr` 外壳支持，并在 real-fdb 验证后补上必要的 clang 数组类型
`uint32_t[256]` / `const uint32_t[256]` 支持；不支持 `&`、`*p++`、postfix `++`
或 `>>`，也不扩展 typed IR emitter。

核心改动：
- `crates/c2r-translator/src/clang_frontend.rs`
  - `ClangExprSkeleton` 新增 `Index { base, index, ty }`。
  - `expr_skeleton_from_ast()` 新增 `ArraySubscriptExpr` 分支，要求 child 恰好是
    `[base, index]`，否则 `invalid_array_subscript_expr` fail-closed。
  - `lower_expr()` 能把 clang index skeleton lower 成现有 `IrExpr::Index`。
  - `ClangTypeKind` 新增 `Array { element, len }`。
  - `type_from_qual_type()` 新增定长/不完整数组解析：
    `uint32_t[256]`、`const uint32_t[256]`、`uint32_t[]`。
  - `lower_type()` 能把 clang array type lower 成现有 `IrTypeKind::Array`。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 `clang_lowering_skeleton_maps_array_subscript_expr`。
  - 新增 `clang_lowering_skeleton_maps_const_array_type`。
  - 新增真实 clang smoke：
    `clang_ast_dump_lowers_array_subscript_expr_when_enabled`。
  - 新增真实 clang smoke：
    `clang_ast_dump_lowers_global_const_array_subscript_when_enabled`。
  - 新增真实 clang fail-closed smoke：
    `clang_ast_dump_rejects_bitand_array_index_expr_when_enabled`。

TDD 红绿过程：
- 红灯 1：`clang_lowering_skeleton_maps_array_subscript_expr` 先失败在
  `ClangExprSkeleton::Index` 不存在。
- 绿灯 1：补 Index skeleton、`ArraySubscriptExpr` parser 和 `IrExpr::Index` lowering 后，
  skeleton 与真实 clang `table[idx]` smoke 均通过。
- real-fdb 中间验证显示 blocker 从 `ArraySubscriptExpr` 推进到
  `unsupported_clang_type: uint32_t[256] is outside the current type skeleton`。
- 红灯 2：`clang_lowering_skeleton_maps_const_array_type` 先失败在
  `ClangTypeKind::Array` 不存在。
- 绿灯 2：补 clang array type skeleton、`T[N]` / `T[]` parser 和 `IrTypeKind::Array`
  lowering 后，真实 clang 全局数组 smoke 通过。
- 负例：`table[(crc ^ idx) & 0xff]` 继续返回 unsupported，message 包含
  `BinaryOperator: opcode &`。

真实 real-fdb 临时 report 推进结果：
- 第 57 节末尾：
  `unsupported_clang_expr: ArraySubscriptExpr: ArraySubscriptExpr is outside the current clang lowering skeleton`。
- 本轮实现 `ArraySubscriptExpr` 后的中间 blocker：
  `unsupported_clang_type: uint32_t[256] is outside the current type skeleton`。
- 本轮最终：
  `unsupported_clang_expr: BinaryOperator: opcode & is outside the current skeleton`。
- 这说明已经跨过 `crc32_tab[...]` 的下标表达式外壳和全局 `uint32_t[256]`
  table 类型，当前真实 blocker 是 index 内部的 `& 0xff`。

本轮并行只读审查结论：
- Dirac：真实 clang AST 中 `ArraySubscriptExpr.inner` 顺序是 base 在前、index 在后；
  `read_table` 的 index 是 `ImplicitCastExpr -> DeclRefExpr idx`，real-fdb 形态的 index
  根节点是 `BinaryOperator opcode="&"`，不是 `*p++` 或 `>>`。
- Heisenberg：`IrExpr::Index` 已存在，最小补法应只加 `ClangExprSkeleton::Index`、
  `ArraySubscriptExpr` branch 和 `lower_expr()` 映射；child 数量异常必须 fail-closed。
- Leibniz：real-fdb 的全局表会暴露 `uint32_t[256]` 类型，需把 clang array type
  映射到已有 `IrTypeKind::Array`；`const uint32_t[256]` 应保留 outer const，
  不要把数组悄悄当指针处理。

已通过命令：
```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_lowering_skeleton_maps_array_subscript_expr -- --nocapture
$env:PATH = 'C:\Program Files\LLVM\bin;' + $env:PATH
$env:LIBCLANG_PATH = 'C:\Program Files\LLVM\bin\libclang.dll'
$env:CLANG_PATH = 'C:\Program Files\LLVM\bin\clang.exe'
$env:C2R_RUN_CLANG_AST_TESTS = '1'
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_ast_dump_lowers_array_subscript_expr_when_enabled -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report type_from_qual_type_maps_ -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_lowering_skeleton_maps_ -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_ast_dump_lowers_global_const_array_subscript_when_enabled -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_ast_dump_rejects_bitand_array_index_expr_when_enabled -- --nocapture
cargo fmt --manifest-path crates/c2r-translator/Cargo.toml
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_run_translator_emit_clang_lowering_report_enables_report_feature validation.tools.test_auto_migrate.AutoMigrateTests.test_real_fdb_calc_crc32_emit_clang_lowering_report_opt_in_writes_temp_artifact validation.tools.test_auto_migrate.AutoMigrateTests.test_cache_identity_records_emit_clang_lowering_report_opt_in
python -B validation/tools/auto_migrate.py --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json --out-root <temp> --skip-c-oracle --skip-rust-check --emit-clang-lowering-report
```

完整结果：
- focused array subscript skeleton test：`1 passed`。
- 私有 clang array type parser tests：`3 passed`。
- skeleton lowering filtered suite：`8 passed`。
- 真实 clang array subscript smoke：`1 passed`。
- 真实 clang global const array smoke：`1 passed`。
- 真实 clang bitand array index 负例：`1 passed`。
- `--features clang-lowering-report` translator crate：lib `3 passed`，
  `bounded_translation` `74 passed`。
- focused Python opt-in tests：`Ran 3 tests ... OK`。
- real-fdb 临时 out-root report：`status=unsupported`，
  `errors[0].kind=unsupported_clang_expr`，
  `errors[0].message="BinaryOperator: opcode & is outside the current skeleton"`。

当前核心翻译功能状态：
- clang AST lowering 已能跨过 real-fdb 的局部声明、指针 cast assignment、
  `crc = crc ^ ~0U;`、`WhileStmt` 外壳、`while(size--)` condition、
  `crc32_tab[...]` 外壳和全局 `uint32_t[256]` table 类型。
- 当前真实 blocker 是循环体 table index 内部的 `BinaryOperator("&")`。
- 后续仍需分层处理 `BinaryOperator("&")`、`UnaryOperator("*")`、postfix `++`、
  `BinaryOperator(">>")` 以及最终把 clang lower 出的 typed IR 与 CRC32 emitter gate 对齐。
- 完整 CRC32 Rust 生成仍不是由真实 clang AST lowering 直接驱动。

下一步建议：
1. 为 `BinaryOperator("&")` 写最小 skeleton/lowering，映射到现有 `IrBinOp::BitAnd`，
   并补真实 clang `table[(crc ^ idx) & 0xff]` smoke 从 unsupported 变 lowered 的测试。
2. 继续保持 fail-closed：`*p++`、postfix `++`、deref 和 `>>` 暂不顺手打开。
3. 用 real-fdb 临时 report 验证 blocker 继续推进；预期下一层会落到 `UnaryOperator("*")`
   或 postfix `++`，而不是直接完成完整 CRC32 lowering。

## 59. 2026-06-26 clang BitAnd expression lowering

本轮承接第 58 节的真实 blocker：只为 clang AST lowering report 增加最小
`BinaryOperator("&")` 支持，映射到现有 `IrBinOp::BitAnd`；不支持 `*p++`、
postfix `++`、deref、`>>`，也不扩展 typed IR emitter。

核心改动：
- `crates/c2r-translator/src/clang_frontend.rs`
  - `ClangBinaryOperator` 新增 `BitAnd`。
  - `expr_skeleton_from_ast()` 的 `BinaryOperator` opcode match 新增
    `Some("&") => ClangBinaryOperator::BitAnd`。
  - `lower_binary_operator()` 新增 `BitAnd -> IrBinOp::BitAnd`。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 `clang_lowering_skeleton_maps_bitand_array_index_expr`。
  - 将真实 clang smoke 改为
    `clang_ast_dump_lowers_bitand_array_index_expr_when_enabled`，验证
    `table[(crc ^ idx) & 0xff]` 能 lower 出 `Index.index = BitAnd(BitXor(...), 255)`。

TDD 红绿过程：
- 红灯：`clang_lowering_skeleton_maps_bitand_array_index_expr` 先失败在
  `ClangBinaryOperator::BitAnd` 不存在。
- 绿灯：补 `BitAnd` enum、clang opcode `"&"` parser 和 `IrBinOp::BitAnd` 映射后，
  skeleton 与真实 clang `table[(crc ^ idx) & 0xff]` smoke 均通过。

真实 real-fdb 临时 report 推进结果：
- 第 58 节末尾：
  `unsupported_clang_expr: BinaryOperator: opcode & is outside the current skeleton`。
- 本轮后：
  `unsupported_clang_expr: UnaryOperator: opcode * is outside the current skeleton`。
- 这说明已经跨过 table index 内部的 `& 0xff`，当前真实 blocker 是
  `crc ^ *p++` 中的 dereference `UnaryOperator("*")`。

本轮并行只读审查结论：
- Euler：当前递归顺序是 lhs 先于 rhs，`ArraySubscriptExpr` 是 base 先、index 后；
  支持 `&` 后会进入 `&` 的 lhs `crc ^ *p++`，再先访问该 `^` 的 rhs `*p++`，
  因而下一条 fail-closed 应是 `UnaryOperator("*")`。`ImplicitCastExpr IntegralCast`
  会被透明剥壳，`>>` 在外层 `^` 的 rhs 上，访问顺序更晚。
- Raman：本轮最小改动只应包含 `ClangBinaryOperator::BitAnd`、opcode `"&"` parser
  和 `lower_binary_operator()` 映射；不应碰 `*p++`、postfix `++`、`>>`、emitter
  或更多二元运算符。

已通过命令：
```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_lowering_skeleton_maps_bitand_array_index_expr -- --nocapture
$env:PATH = 'C:\Program Files\LLVM\bin;' + $env:PATH
$env:LIBCLANG_PATH = 'C:\Program Files\LLVM\bin\libclang.dll'
$env:CLANG_PATH = 'C:\Program Files\LLVM\bin\clang.exe'
$env:C2R_RUN_CLANG_AST_TESTS = '1'
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_ast_dump_lowers_bitand_array_index_expr_when_enabled -- --nocapture
cargo fmt --manifest-path crates/c2r-translator/Cargo.toml
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_run_translator_emit_clang_lowering_report_enables_report_feature validation.tools.test_auto_migrate.AutoMigrateTests.test_real_fdb_calc_crc32_emit_clang_lowering_report_opt_in_writes_temp_artifact validation.tools.test_auto_migrate.AutoMigrateTests.test_cache_identity_records_emit_clang_lowering_report_opt_in
python -B validation/tools/auto_migrate.py --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json --out-root <temp> --skip-c-oracle --skip-rust-check --emit-clang-lowering-report
```

完整结果：
- focused BitAnd skeleton test：`1 passed`。
- 真实 clang BitAnd array index smoke：`1 passed`。
- `--features clang-lowering-report` translator crate：lib `3 passed`，
  `bounded_translation` `75 passed`。
- focused Python opt-in tests：`Ran 3 tests ... OK`。
- real-fdb 临时 out-root report：`status=unsupported`，
  `errors[0].kind=unsupported_clang_expr`，
  `errors[0].message="UnaryOperator: opcode * is outside the current skeleton"`。

当前核心翻译功能状态：
- clang AST lowering 已能跨过 real-fdb 的局部声明、指针 cast assignment、
  `crc = crc ^ ~0U;`、`WhileStmt` 外壳、`while(size--)` condition、
  `crc32_tab[...]` 外壳、全局 `uint32_t[256]` table 类型和 `& 0xff`。
- 当前真实 blocker 是 `*p++` 的外层 deref `UnaryOperator("*")`。
- 后续仍需分层处理 `UnaryOperator("*")`、postfix `++`、`BinaryOperator(">>")`
  以及最终把 clang lower 出的 typed IR 与 CRC32 emitter gate 对齐。
- 完整 CRC32 Rust 生成仍不是由真实 clang AST lowering 直接驱动。

下一步建议：
1. 为 `UnaryOperator("*")` 写最小 skeleton/lowering，映射到现有 `IrExpr::Deref`，
   并补真实 clang `*p` 或 `table[(crc ^ *p) & 0xff]` smoke。
2. 继续保持 fail-closed：postfix `++` 暂不顺手打开；如果 `*p++` 的 operand 先卡到
   `UnaryOperator("++")`，下轮再单独处理。
3. 继续用 real-fdb 临时 report 验证 blocker 推进；预期下一层会落到 postfix `++`
   或稍后的 `BinaryOperator(">>")`。

## 60. 2026-06-26 clang pointer dereference lowering

本轮承接第 59 节的真实 blocker：只为 clang AST lowering report 增加最小
`UnaryOperator("*")` 支持，映射到现有 `IrExpr::Deref`；不支持 postfix `++`、
`>>`，也不扩展 typed IR emitter。

核心改动：
- `crates/c2r-translator/src/clang_frontend.rs`
  - `ClangExprSkeleton` 新增 `Deref { ptr, ty }`。
  - `expr_skeleton_from_ast()` 在 `UnaryOperator opcode "*"` 时生成
    `ClangExprSkeleton::Deref`，operand 继续递归 lower。
  - `lower_expr()` 新增 `Deref -> IrExpr::Deref` 映射。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 `clang_lowering_skeleton_maps_pointer_deref_expr`。
  - 新增真实 clang smoke：
    `clang_ast_dump_lowers_pointer_deref_expr_when_enabled`，覆盖
    `uint8_t read_byte(const uint8_t *p) { return *p; }`。
  - 新增真实 clang 组合 smoke：
    `clang_ast_dump_lowers_deref_in_bitand_array_index_expr_when_enabled`，覆盖
    `table[(crc ^ *p) & 0xff]`。

TDD 红绿过程：
- 红灯：`clang_lowering_skeleton_maps_pointer_deref_expr` 先失败在
  `ClangExprSkeleton::Deref` 不存在。
- 绿灯：补 Deref skeleton、clang `UnaryOperator("*")` parser 和 `IrExpr::Deref`
  lowering 后，skeleton、真实 clang `*p` smoke 和 `table[(crc ^ *p) & 0xff]`
  组合 smoke 均通过。

真实 real-fdb 临时 report 推进结果：
- 第 59 节末尾：
  `unsupported_clang_expr: UnaryOperator: opcode * is outside the current skeleton`。
- 本轮后：
  `unsupported_clang_expr: UnaryOperator: opcode ++ is outside the current skeleton`。
- 这说明已经跨过 `*p++` 的外层 dereference，当前真实 blocker 是 operand
  里的 postfix increment `p++`。

本轮并行只读审查结论：
- Beauvoir：`*p++` 的 clang AST 形状是
  `UnaryOperator("*") -> UnaryOperator("++" isPostfix=true) -> DeclRefExpr(p)`；
  支持 `*` 后，按当前递归顺序下一条 fail-closed 应是 `UnaryOperator: opcode ++`，
  而不是 `>>`。
- Descartes：typed IR 已有 `IrExpr::Deref`，本轮只需要新增 clang deref skeleton、
  `UnaryOperator("*")` parser 和 `lower_expr()` 映射；不要碰 postfix `++`、`>>`、
  emitter、真实 full loop 或 evidence 产物。

已通过命令：
```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_lowering_skeleton_maps_pointer_deref_expr -- --nocapture
$env:PATH = 'C:\Program Files\LLVM\bin;' + $env:PATH
$env:LIBCLANG_PATH = 'C:\Program Files\LLVM\bin\libclang.dll'
$env:CLANG_PATH = 'C:\Program Files\LLVM\bin\clang.exe'
$env:C2R_RUN_CLANG_AST_TESTS = '1'
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_ast_dump_lowers_pointer_deref_expr_when_enabled -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_ast_dump_lowers_deref_in_bitand_array_index_expr_when_enabled -- --nocapture
cargo fmt --manifest-path crates/c2r-translator/Cargo.toml
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_run_translator_emit_clang_lowering_report_enables_report_feature validation.tools.test_auto_migrate.AutoMigrateTests.test_real_fdb_calc_crc32_emit_clang_lowering_report_opt_in_writes_temp_artifact validation.tools.test_auto_migrate.AutoMigrateTests.test_cache_identity_records_emit_clang_lowering_report_opt_in
python -B validation/tools/auto_migrate.py --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json --out-root <temp> --skip-c-oracle --skip-rust-check --emit-clang-lowering-report
```

完整结果：
- focused deref skeleton test：`1 passed`。
- 真实 clang pointer deref smoke：`1 passed`。
- 真实 clang deref + bitand array index smoke：`1 passed`。
- `--features clang-lowering-report` translator crate：lib `3 passed`，
  `bounded_translation` `78 passed`。
- focused Python opt-in tests：`Ran 3 tests ... OK`。
- real-fdb 临时 out-root report：`status=unsupported`，
  `errors[0].kind=unsupported_clang_expr`，
  `errors[0].message="UnaryOperator: opcode ++ is outside the current skeleton"`。

当前核心翻译功能状态：
- clang AST lowering 已能跨过 real-fdb 的局部声明、指针 cast assignment、
  `crc = crc ^ ~0U;`、`WhileStmt` 外壳、`while(size--)` condition、
  `crc32_tab[...]` 外壳、全局 `uint32_t[256]` table 类型、`& 0xff`
  和 `*p++` 的 outer deref。
- 当前真实 blocker 是 postfix `++`。
- 后续仍需分层处理 postfix `++`、`BinaryOperator(">>")`，以及最终把 clang lower
  出的 typed IR 与 CRC32 emitter gate 对齐。
- 完整 CRC32 Rust 生成仍不是由真实 clang AST lowering 直接驱动。

下一步建议：
1. 为 `UnaryOperator("++") isPostfix=true` 写最小 skeleton/lowering，映射到现有
   `IrExpr::IncDec { op: Inc, prefix: false }`。
2. 同时保留 fail-closed：prefix `++`、复杂 lvalue 和 `++` 出现在非当前表达式形态时不要顺手放开。
3. 用 real-fdb 临时 report 验证 blocker 推进；预期下一层可能落到 `BinaryOperator(">>")`。

## 61. 2026-06-26 clang postfix increment lowering

本轮承接第 60 节的真实 blocker：只为 clang AST lowering report 增加最小
`UnaryOperator("++") isPostfix=true` 支持，映射到现有
`IrExpr::IncDec { op: Inc, prefix: false }`；不支持 prefix `++`，不实现
`BinaryOperator(">>")`，也不扩展 typed IR emitter。

核心改动：
- `crates/c2r-translator/src/clang_frontend.rs`
  - `ClangIncDecOperator` 新增 `Inc`。
  - `expr_skeleton_from_ast()` 将 `UnaryOperator("--")` 专用分支推广为
    postfix `++` / `--` 共用分支；prefix `++` / `--` 继续返回
    `Unsupported`。
  - `lower_inc_dec_operator()` 新增 `Inc -> IrIncDecOp::Inc`。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 `clang_lowering_skeleton_maps_postfix_increment_in_deref_expr`。
  - 新增真实 clang smoke：
    `clang_ast_dump_lowers_postfix_increment_deref_expr_when_enabled`。
  - 新增真实 clang 组合 smoke：
    `clang_ast_dump_lowers_postfix_increment_deref_in_bitand_array_index_expr_when_enabled`，
    覆盖 `table[(crc ^ *p++) & 0xff]` 这条不含 `>>` 的子树。
  - 新增真实 clang fail-closed smoke：
    `clang_ast_dump_rejects_prefix_increment_deref_expr_when_enabled`。

TDD 红绿过程：
- 红灯：`clang_lowering_skeleton_maps_postfix_increment_in_deref_expr` 先失败在
  `ClangIncDecOperator::Inc` 不存在。
- 绿灯：补 clang `Inc` enum、postfix `++` parser 和 `IrIncDecOp::Inc`
  映射后，skeleton、真实 `*p++` smoke、组合 `table[(crc ^ *p++) & 0xff]`
  smoke 和 prefix `++` 负例均通过。

真实 real-fdb 临时 report 推进结果：
- 第 60 节末尾：
  `unsupported_clang_expr: UnaryOperator: opcode ++ is outside the current skeleton`。
- 本轮后：
  `unsupported_clang_expr: BinaryOperator: opcode >> is outside the current skeleton`。
- 这说明 clang AST lowering 已经跨过 `crc32_tab[(crc ^ *p++) & 0xff]`
  的 table lookup、`&`、`^`、outer deref 和 postfix `p++`，当前真实 blocker
  是外层 CRC 更新表达式右侧的 `crc >> 8`。

本轮并行只读审查结论：
- Maxwell：只补 postfix `++` 后，下一层 fail-closed 应落到
  `BinaryOperator(">>")`；typed IR 不是立即 blocker，因为 `IrBinOp::Shr`
  和 `IrIncDecOp::Inc` 已存在。
- Halley：最小生产改动应只包含 `ClangIncDecOperator::Inc`、
  `UnaryOperator` postfix `++` / `--` 分支和 `lower_inc_dec_operator()` 映射；
  不要碰 `>>`、emitter 或 validation evidence。

已通过命令：
```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_lowering_skeleton_maps_postfix_increment_in_deref_expr -- --nocapture
$env:PATH = 'C:\Program Files\LLVM\bin;' + $env:PATH
$env:LIBCLANG_PATH = 'C:\Program Files\LLVM\bin\libclang.dll'
$env:CLANG_PATH = 'C:\Program Files\LLVM\bin\clang.exe'
$env:C2R_RUN_CLANG_AST_TESTS = '1'
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_ast_dump_lowers_postfix_increment_deref_expr_when_enabled -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_ast_dump_lowers_postfix_increment_deref_in_bitand_array_index_expr_when_enabled -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_ast_dump_rejects_prefix_increment_deref_expr_when_enabled -- --nocapture
cargo fmt --manifest-path crates/c2r-translator/Cargo.toml
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_run_translator_emit_clang_lowering_report_enables_report_feature validation.tools.test_auto_migrate.AutoMigrateTests.test_real_fdb_calc_crc32_emit_clang_lowering_report_opt_in_writes_temp_artifact validation.tools.test_auto_migrate.AutoMigrateTests.test_cache_identity_records_emit_clang_lowering_report_opt_in
python -B validation/tools/auto_migrate.py --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json --out-root <temp> --skip-c-oracle --skip-rust-check --emit-clang-lowering-report
```

完整结果：
- focused postfix increment skeleton test：`1 passed`。
- 真实 clang postfix increment deref smoke：`1 passed`。
- 真实 clang postfix increment deref + bitand array index smoke：`1 passed`。
- 真实 clang prefix increment 负例：`1 passed`。
- `--features clang-lowering-report` translator crate：lib `3 passed`，
  `bounded_translation` `82 passed`。
- focused Python opt-in tests：`Ran 3 tests ... OK`。
- real-fdb 临时 out-root report：`status=unsupported`，
  `errors[0].kind=unsupported_clang_expr`，
  `errors[0].message="BinaryOperator: opcode >> is outside the current skeleton"`。

当前核心翻译功能状态：
- clang AST lowering 已能跨过 real-fdb 的局部声明、指针 cast assignment、
  `crc = crc ^ ~0U;`、`WhileStmt` 外壳、`while(size--)` condition、
  `crc32_tab[...]` 外壳、全局 `uint32_t[256]` table 类型、`& 0xff`、
  `*p++` 的 outer deref 和 postfix `p++`。
- 当前真实 blocker 是 `BinaryOperator(">>")`。
- 完整 CRC32 Rust 生成仍不是由真实 clang AST lowering 直接驱动；下一轮应只为
  `BinaryOperator(">>")` 写最小 skeleton/lowering，映射到现有 `IrBinOp::Shr`，
  再用 real-fdb report 验证是否进入 emitter gate 对齐阶段。

## 62. 2026-06-26 clang shift-right lowering

本轮承接第 61 节的真实 blocker：只为 clang AST lowering report 增加最小
`BinaryOperator(">>")` 支持，映射到现有 `IrBinOp::Shr`；不扩展其它二元运算，
不调整 typed IR emitter / CRC32 matcher，也不触碰 validation evidence。

核心改动：
- `crates/c2r-translator/src/clang_frontend.rs`
  - `ClangBinaryOperator` 新增 `Shr`。
  - `expr_skeleton_from_ast()` 的 `BinaryOperator` opcode match 新增
    `Some(">>") => ClangBinaryOperator::Shr`。
  - `lower_binary_operator()` 新增 `Shr -> IrBinOp::Shr`。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 `clang_lowering_skeleton_maps_shift_right_expr`。
  - 新增真实 clang smoke：
    `clang_ast_dump_lowers_shift_right_expr_when_enabled`。
  - 新增真实 clang 组合 smoke：
    `clang_ast_dump_lowers_crc_update_expr_with_postinc_and_shift_when_enabled`，
    覆盖 `table[(crc ^ *p++) & 0xff] ^ (crc >> 8)`。

TDD 红绿过程：
- 红灯：`clang_lowering_skeleton_maps_shift_right_expr` 先失败在
  `ClangBinaryOperator::Shr` 不存在。
- 绿灯：补 clang `Shr` enum、opcode `">>"` parser 和 `IrBinOp::Shr`
  映射后，skeleton、真实 `crc >> 8` smoke 和真实 CRC update RHS smoke 均通过。

真实 real-fdb 临时 report 推进结果：
- 第 61 节末尾：
  `unsupported_clang_expr: BinaryOperator: opcode >> is outside the current skeleton`。
- 本轮后：
  `status=lowered`，`errors=[]`。
- 当前 report artifact 仍是 diagnostic/report 路径；临时 report 里
  `function_ir` 字段为 `null`，所以这只能说明 clang AST lowering front-end
  已跨过当前真实语法 blocker，不能声明真实 clang-lowered IR 已驱动 Rust 生成。

本轮并行只读审查结论：
- Laplace：`>>` 的最小改动面就是 `ClangBinaryOperator::Shr`、opcode `">>"`
  mapping 和 `lower_binary_operator()` 三处；不要顺手实现 `<<`、`|`、`-` 等其它运算，
  也不要碰 signed shift 语义建模或 evidence。
- Volta：只补 `>>` 很可能让 real-fdb report 从 unsupported 变为 lowered，但这不等于
  `emit_rust_from_ir` 已接受真实 clang-lowered IR；当前主翻译路径的 CRC32 成功仍来自
  C 源字符串识别后构造的硬编码 typed IR，emitter gate 仍是刻意严格的
  `is_crc32_byte_cursor_ir()`。

已通过命令：
```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_lowering_skeleton_maps_shift_right_expr -- --nocapture
$env:PATH = 'C:\Program Files\LLVM\bin;' + $env:PATH
$env:LIBCLANG_PATH = 'C:\Program Files\LLVM\bin\libclang.dll'
$env:CLANG_PATH = 'C:\Program Files\LLVM\bin\clang.exe'
$env:C2R_RUN_CLANG_AST_TESTS = '1'
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_ast_dump_lowers_shift_right_expr_when_enabled -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_ast_dump_lowers_crc_update_expr_with_postinc_and_shift_when_enabled -- --nocapture
python -B validation/tools/auto_migrate.py --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json --out-root <temp> --skip-c-oracle --skip-rust-check --emit-clang-lowering-report
cargo fmt --manifest-path crates/c2r-translator/Cargo.toml
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_run_translator_emit_clang_lowering_report_enables_report_feature validation.tools.test_auto_migrate.AutoMigrateTests.test_real_fdb_calc_crc32_emit_clang_lowering_report_opt_in_writes_temp_artifact validation.tools.test_auto_migrate.AutoMigrateTests.test_cache_identity_records_emit_clang_lowering_report_opt_in
```

完整结果：
- focused shift-right skeleton test：`1 passed`。
- 真实 clang shift-right smoke：`1 passed`。
- 真实 clang CRC update RHS smoke：`1 passed`。
- real-fdb 临时 out-root clang lowering report：`status=lowered`，`errors=[]`。
- `--features clang-lowering-report` translator crate：lib `3 passed`，
  `bounded_translation` `85 passed`。
- focused Python opt-in tests：`Ran 3 tests ... OK`。

当前核心翻译功能状态：
- clang AST lowering report 已能跨过 real-fdb `fdb_calc_crc32` 目前已知的前端语法
  blocker：局部声明、指针 cast assignment、`crc = crc ^ ~0U;`、`WhileStmt`、
  `while(size--)`、`crc32_tab[...]`、全局 `uint32_t[256]` table、`& 0xff`、
  `*p++`、postfix `p++` 和 `crc >> 8`。
- 这还不是完整“真实 clang AST lowering -> typed IR -> 可编译 Rust”的闭环。
- 下一步建议：新增一个整函数测试，直接把真实 clang-lowered `fdb_calc_crc32`
  的 `IrFunction` 传给 `emit_rust_from_ir`，先观察 fail-closed 的真实形状差异；
  然后只按实际 diff 调整 `is_crc32_byte_cursor_ir()` 或接线 report/translation 路径。

## 63. 2026-06-26 clang-lowered typed IR rust draft path

本轮承接第 62 节：`>>` 之后 real-fdb clang lowering report 已经是
`status=lowered`、`errors=[]`，下一步不再继续扩前端语法点，而是验证
"真实 clang-lowered IR -> typed IR emitter -> Rust draft" 这条端到端路径。

核心改动：
- `crates/c2r-translator/src/lib.rs`
  - `write_translation_artifacts()` 在启用 `clang-lowering-report` feature 时先走
    `translate_slice_with_optional_clang_lowered_ir()`。
  - 新路径依次执行 `ClangParseSpec::from_slice_spec()`、
    `lower_function_from_clang_parse_spec_report()`、取 `function_ir`、
    `typed_ir::emit_rust_from_ir()`。
  - 成功时写入 `translation_rule_ids=["clang-lowered-typed-ir"]`。
  - 任一步失败都会 fail-closed 回落到原 `translate_slice()`，不改变默认非 feature
    行为。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 synthetic full `fdb_calc_crc32` 的真实 clang smoke：直接把
    `lower_function_from_clang_ast_dump_report()` 产出的 `function_ir` 传给
    `emit_rust_from_ir()`。
  - 新增真实 validation slice spec smoke：从
    `validation/slice-specs/flashdb-real-fdb-calc-crc32.json` 构造当前
    `SliceSpec`，经 `ClangParseSpec` 和 lowering report 后再进入
    `emit_rust_from_ir()`。
  - 新增 artifact path smoke：临时真实 `src/fdb_utils.c` 是完整 CRC32，
    但 `spec.c_source` 故意写成 `{ return crc; }`，证明 `rust-draft.rs`
    中的 `crc32_update_byte()` 不是旧字符串识别路径生成的。

边界声明：
- 这只证明在 `clang-lowering-report` opt-in 下，真实 clang-lowered
  `fdb_calc_crc32` 的 `function_ir` 已经能驱动当前 typed emitter 生成 CRC32 Rust
  draft。
- 这仍然不是 semantic pass，不声明行为等价，不把 diagnostic-only 的 lowering report
  扩大成 accepted evidence。
- `auto_migrate` 仍应按既有 evidence/rust-check/oracle 规则决定
  `generated_draft_semantic_pass`，本轮没有把临时 report 提升为验收证据。

已通过命令：
```powershell
cargo fmt --manifest-path crates/c2r-translator/Cargo.toml
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_run_translator_emit_clang_lowering_report_enables_report_feature validation.tools.test_auto_migrate.AutoMigrateTests.test_real_fdb_calc_crc32_emit_clang_lowering_report_opt_in_writes_temp_artifact validation.tools.test_auto_migrate.AutoMigrateTests.test_cache_identity_records_emit_clang_lowering_report_opt_in
python -B validation/tools/auto_migrate.py --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json --out-root <temp> --skip-c-oracle --skip-rust-check --emit-clang-lowering-report
```

完整结果：
- `--features clang-lowering-report` translator crate：lib `3 passed`，
  `bounded_translation` `88 passed`。
- focused Python opt-in tests：`Ran 3 tests ... OK`。
- real-fdb 临时 out-root：`report_status=lowered`、`report_errors=[]`、
  `lowering_report_status=lowered`、`rust_has_crc32_update_byte=true`、
  `rust_has_crc32_table=false`。

当前核心翻译功能状态：
- clang 前端已经跨过 real-fdb `fdb_calc_crc32` 已知语法 blocker，并能产出可被当前
  CRC32 typed emitter 接收的 `IrFunction`。
- `write_translation_artifacts()` 在 `clang-lowering-report` opt-in 下已经能用这份真实
  clang-lowered IR 写出 CRC32 Rust draft。
- 下一步建议不要再做前端 blocker 猜测；应补强 clang-lowered path 的
  type-map/cfg/evidence 接线，或者运行真实 rust-check/oracle 路径来推进 semantic pass。

## 64. 2026-06-26 clang-lowered typed IR evidence path

本轮承接第 63 节：真实 clang-lowered `IrFunction` 已能生成 CRC32 Rust draft，但
`try_translate_slice_with_clang_lowered_ir()` 成功时只填了 `rust_code` 和 plan rule，
`type_map`、`cfg`、`pointer_graph` 仍是空结构。这会让 `clang-lowered-typed-ir`
路径缺少同源 evidence，后续 Python normalize 还可能把空 type-map 记录为
`recorded`、把真实 pointer slice 误判为 `not_applicable`。

核心改动：
- `crates/c2r-translator/src/lib.rs`
  - 新增 `record_clang_lowered_ir_evidence()`，在 clang-lowered typed IR 成功生成
    Rust draft 后，从同一个 `typed_ir::IrFunction` 派生最小
    `TypeMapEvidence`、`CfgEvidence` 和 `PointerGraphEvidence`。
  - type-map 覆盖 return、params 和局部 `Decl`，继续复用既有 `record_type_mapping()`
    与 `map_c_type()`，避免发明第二套 Rust type mapping。
  - cfg 覆盖顶层 typed IR 语句种类、return/fallthrough terminator 和
    `entry->while-N` / `entry->return-N` 边。
  - pointer graph 目前只保守覆盖 pointer 参数；只有在同一个 typed IR body 中确认
    `p = (const uint8_t *)buf` cursor 来源和 `*p++` read 都存在时，才对 real-fdb 的
    `buf` 记录 `borrowed_input`、`&[u8]`、`*p++` read effect 和
    `byte_cursor_post_increment_read` boundary decision。
  - 成功路径保留 fail-closed fallback：clang parse、lowering、typed emitter 或 evidence
    之外的任一步失败时仍回落原 `translate_slice()`。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 扩展
    `clang_lowering_report_feature_can_drive_rust_draft_from_clang_lowered_ir_when_enabled`。
  - 该测试继续使用真实临时 `src/fdb_utils.c`，同时把 `spec.c_source` 故意写成
    `{ return crc; }`，并新增断言：
    - `type-map` 中有 `buf -> &[u8]`。
    - `cfg` statement kinds 包含 `while`。
    - `pointer-graph` status 是 `recorded`。
    - `buf` 节点包含 `borrowed_input`、`&[u8]` 和
      `*p++` read effect、`byte_cursor_post_increment_read`。
  - 新增私有单元负例：
    `clang_lowered_pointer_graph_does_not_infer_byte_cursor_from_buf_name_only`，
    证明只有 `buf` 参数但没有 IR body byte cursor 读时，不会记录
    `*p++` 或 `byte_cursor_post_increment_read`。

TDD 红绿过程：
- 红灯：
```powershell
$env:PATH = 'C:\Program Files\LLVM\bin;' + $env:PATH
$env:LIBCLANG_PATH = 'C:\Program Files\LLVM\bin\libclang.dll'
$env:CLANG_PATH = 'C:\Program Files\LLVM\bin\clang.exe'
$env:C2R_RUN_CLANG_AST_TESTS = '1'
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_lowering_report_feature_can_drive_rust_draft_from_clang_lowered_ir_when_enabled -- --nocapture
```
失败点：`type_map["type_map"]["mappings"]` 里找不到 `buf -> &[u8]`。
- review 后补充红灯：
```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_lowered_pointer_graph_does_not_infer_byte_cursor_from_buf_name_only -- --nocapture
```
失败点：有 `buf` 参数但没有 `*p++` 的 IR 仍被硬编码记录了 `read_effects=["*p++"]`。
- 绿灯：实现 body-derived byte cursor evidence 后，两条 focused 测试均 `1 passed`。

已通过命令：
```powershell
cargo fmt --manifest-path crates/c2r-translator/Cargo.toml
$env:PATH = 'C:\Program Files\LLVM\bin;' + $env:PATH
$env:LIBCLANG_PATH = 'C:\Program Files\LLVM\bin\libclang.dll'
$env:CLANG_PATH = 'C:\Program Files\LLVM\bin\clang.exe'
$env:C2R_RUN_CLANG_AST_TESTS = '1'
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_lowering_report_feature_can_drive_rust_draft_from_clang_lowered_ir_when_enabled -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_run_translator_emit_clang_lowering_report_enables_report_feature validation.tools.test_auto_migrate.AutoMigrateTests.test_real_fdb_calc_crc32_emit_clang_lowering_report_opt_in_writes_temp_artifact validation.tools.test_auto_migrate.AutoMigrateTests.test_cache_identity_records_emit_clang_lowering_report_opt_in
python -B validation/tools/auto_migrate.py --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json --out-root <temp> --skip-c-oracle --skip-rust-check --emit-clang-lowering-report
```

完整结果：
- `--features clang-lowering-report` translator crate：lib `4 passed`，
  `bounded_translation` `88 passed`。
- default feature translator crate：`bounded_translation` `35 passed`。
- focused Python opt-in tests：`Ran 3 tests ... OK`。
- real-fdb 临时 out-root：
  - `report_status=lowered`。
  - plan rules 包含 `clang-lowered-typed-ir`、
    `byte-cursor-post-increment-read`、`crc32-byte-cursor-loop`。
  - type-map symbols 包含 `return -> u32`、`crc -> u32`、`buf -> &[u8]`、
    `size -> usize`、`p -> &[u8]`。
  - cfg statement kinds 包含 `primitive_declaration`、`assignment`、`while`、
    `return`。
  - pointer graph status 为 `recorded`，Rust 原始 `buf` 节点记录 `borrowed_input`、
    `&[u8]`、`*p++` read effect 和 `byte_cursor_post_increment_read`；Python normalize
    后的 pointer graph 仍负责派生 `length_companion=size`。

本轮并行只读核对结论：
- Bohr：下一步优先补强 clang-lowered path 的 type-map/cfg/pointer/evidence，
  不要先推进 rust-check/oracle；Rust 侧成功路径空 evidence 是当前真实缺口。
- Averroes：启用 clang-lowered typed IR 后，real-fdb Rust draft 和 rust-check 已经能过；
  下一层 blocker 是 C oracle/diff 仍停在 draft：
  `c-oracle-status.status=DRAFT_GENERATED`、
  `toolchain_status=COMPILE_SUCCEEDED_NOT_ORACLE`、
  `output_gate.status=matched_not_oracle`、validation profile `incomplete`。

当前核心翻译功能状态：
- real-fdb `fdb_calc_crc32` 已完成从真实 clang AST lowering 到 typed IR、Rust draft、
  type-map、cfg、pointer graph 的同源最小闭环。
- 这仍不是 semantic pass；`generated_draft_semantic_pass=false` 仍然正确。
- 下一步核心模块建议：把当前 `matched_not_oracle` 的 C harness 输出推进成可审计的
  generated-candidate oracle/diff gate，生成 C oracle output JSON、Rust replay output、
  schema-aware diff 和 negative diff，再让 validation profile 重新计算。
