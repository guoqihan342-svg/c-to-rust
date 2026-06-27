# 核心翻译架构

本页记录当前 `c-to-rust` 核心翻译链路、关键代码位置和 FlashDB crc32 泛化进度。英文镜像见 `core-translation-architecture.en.md`。

## 架构图

```mermaid
flowchart TD
    C["C 源码 / compile_commands.json"] --> Clang["clang_frontend.rs<br/>clang AST dump 前端"]
    Clang --> Skeleton["clang skeleton AST 子集"]
    Skeleton --> IR["typed IR: IrFunction / IrStmt / IrExpr / IrType"]
    Clang --> Globals["readonly globals: Vec<IrGlobal><br/>static const integer arrays"]
    IR --> EmitCtx["typed_ir.rs<br/>emit_rust_from_ir_with_globals(function, globals)"]
    Globals --> EmitCtx
    EmitCtx --> RouteMeta["translation_route.rs<br/>CandidateRouteDecision"]
    RouteMeta --> Generic["GenericTypedIr<br/>generic typed IR emitter"]
    RouteMeta --> Unsupported["Unsupported<br/>no Rust candidate"]
    Generic --> Rust["safe Rust draft"]
    Rust --> Rustc["rustc smoke / cargo tests"]
    Rustc --> Validation["validation pipeline<br/>route_decision / validation_profile / evidence gates"]

    Generic --> Supported["当前 generic 覆盖:
    scalar decl/assign/if/while,
    narrow scalar-integer ops: binary + - * / % & | ^ << >>, signed unary -
    (candidate generation only),
    clang-lowered scalar compound assignment family,
    clang-preserved value-position integer casts,
    fixed-width integer aliases,
    multi VarDecl body expansion,
    assigned uninitialized scalar locals,
    condition + narrow value-position comparisons,
    condition + narrow value-position logical !,
    condition + narrow value-position short-circuit && ||,
    value-position scalar ?: / ConditionalOperator,
    scoped scalar for loops,
    const pointer slices,
    readonly pointer NULL checks,
    readonly pointer *p and *(p+i) reads,
    mutable pointer *out/out[i]/ *(out+i) writes,
    readonly global const integer arrays,
    local fixed integer array reads/writes,
    table index via slice param or global,
    bounded direct calls,
    nested byte *p++ prelude,
    size_t while(size--)"]
    Validation --> Semantic["semantic_pass 只由验证流水线决定"]
```

## 核心代码位置

- `crates/c2r-translator/src/clang_frontend.rs`
  - 读取真实 clang AST dump JSON。
  - 把支持的 C AST 节点 lowering 成紧凑的 clang skeleton。
  - 把 skeleton 节点转换成 typed IR。
  - 现在通过 `type_from_qual_type()` 支持固定宽度整数 typedef aliases：`int8_t`、`int16_t`、`int32_t`、`int64_t`、`uint8_t`、`uint16_t`、`uint32_t`、`uint64_t`，并精确支持 `signed char` 作为 signed 8-bit integer；`short` / `long long` 等其他目标相关 spelling 仍不当作 fixed-width typedef。
  - 现在还会收集顶层 `static const` 固定长度整数数组 initializer，输出为 `ClangLoweringReport.globals: Vec<IrGlobal>`。
  - `compound_body_skeleton_from_ast()` 现在会把普通 compound body 中一个 `DeclStmt` 的多个简单 `VarDecl` 按源码顺序展开为多个 `ClangStmtSkeleton::Decl`；`for_init_stmt_skeletons_from_ast()` 对 `ForStmt` init 中的 `DeclStmt` 复用同一个多 `VarDecl` 展开 helper，assignment init 仍是一元素 vec。
  - 现在也会把局部固定长度整数数组 `InitListExpr` lowering 成 `IrExpr::ArrayLiteral`，但只接受元素数量等于数组长度、且元素为纯整数字面量或整型 cast 包裹整数字面量的一维整数数组。
  - 现在也会把 clang `NullToPointer` cast 包裹的整数零 lowering 成 typed IR null pointer literal，用于窄化的指针参数 presence check。
  - 现在会通过 `value_expr_skeleton_from_ast` 和二元 operand cast-preservation 保留 declaration initializer、assignment RHS、return value 和普通 binary operand 中的 clang `IntegralCast` / `IntegralPromotion` 包裹，让 typed IR emitter 能证明并发射整数 `as` cast，而不是静默丢掉 mixed signedness 或 promotion 信息。
  - 现在会把 `CompoundAssignOperator` 的 result type 和 compute type 带入 `ClangStmtSkeleton::CompoundAssign`，在 simple scalar variable target 上支持 clang 已证明的窄化整数 promotion/truncation，同时继续拒绝 target/result 不一致和 compute-lhs/compute-result 不一致。
  - 现在会把普通 clang `ConditionalOperator` / `?:` lowering 成 `ClangExprSkeleton::Conditional`，并显式拒绝 GNU omitted-middle `BinaryConditionalOperator`。
  - 现在会把窄化 clang `ForStmt` lowering 成 `ClangStmtSkeleton::For`，只接受简单 scalar declaration/assignment init（含多个简单 `VarDecl` declarator）、condition、assignment/compound-assignment/postfix-or-prefix inc-dec step 和现有 body 子集；`DoStmt` 会 lowering 成 `ClangStmtSkeleton::DoWhile`；`BreakStmt` 会 lowering 成 loop-body `IrStmt::Break`，`ContinueStmt` 会 lowering 成窄化 loop-body `IrStmt::Continue`；condition variable slot、空 condition/step 等仍 fail closed。
  - 关键函数：`lower_function_from_clang_ast_dump_report`、`lower_function_from_clang_parse_spec_report`、`readonly_globals_from_ast`、`readonly_global_from_toplevel_var_decl`、`integer_literal_init_list_values`、`value_expr_skeleton_from_ast`、`expr_skeleton_from_ast_with_options`、`init_list_expr_skeleton_from_ast`、`for_stmt_skeleton_from_ast`、`for_init_stmt_skeletons_from_ast`、`lower_stmt`、`lower_expr`。
- `crates/c2r-translator/src/typed_ir.rs`
  - 定义 `IrFunction`、`IrStmt`、`IrExpr`、`IrType`、`IrGlobal`、`IrGlobalInit`。
  - `emit_rust_from_ir()` 仍保留无 globals 的兼容入口。
  - `emit_rust_from_ir_with_globals(function, globals)` 是 clang lowering 路径的核心入口，会生成 `EmittedRust { rust, route }`。
  - generic emitter 已支持 readonly global const integer array 的 Rust `const` 输出和 `CRC32_TABLE[...]` 形式的下标访问。
  - generic emitter 现在会在 Rust 发射前运行保守 definite-assignment guard；无 initializer 的标量局部声明只有在支持子集内能证明读取前已有赋值时，才会发射为 `let mut x: T;`。
  - generic emitter 也支持 typed IR 层的局部固定长度整数数组字面量、下标读取和局部数组元素赋值，生成 Rust `[T; N]` 局部数组，并在元素被写入时发射 `let mut`。
  - generic emitter 支持窄化的 readonly pointer null-presence 表面：`const int *values; return values != NULL;` 发射为 `values: Option<&[i32]>` 加 `.is_some()`；同一个 nullable 参数如果出现在直接 null comparison 之外会 fail closed。
  - generic emitter 支持窄化的 readonly pointer dereference read：`const uint8_t *p; return *p;` 发射为 `p: &[u8]` 和 `return p[0usize];`；bounded offset-deref read 例如 `return *(p+i);` / `return *(i+p);` 发射为 `return p[i as usize];`。这只覆盖 readonly integer pointer 的直接读或无副作用整数 offset 读；非写目标的 mutable pointer read、其他 pointer arithmetic、nullable pointer null check 后继续 deref/index 仍 fail closed。
  - generic emitter 支持窄化的 mutable integer pointer output write：只有函数参数 `T *out` 确实作为写目标出现时才发射为 `out: &mut [T]`，并支持 `*out = value`、`out[i] = value`、`*(out+i) = value` / `*(i+out) = value` 生成 Rust slice 写入。元素类型必须是当前支持的整数标量，offset 必须是无副作用的整数字面量/变量/cast；`const T *` 写入、复杂 offset、compound/update 写、nullable pointer、pointer escape、mutable pointer read、alias/ownership 证明和 semantic acceptance 仍 fail closed。
  - generic emitter 支持一等 lazy `IrExpr::Conditional` 的纯整数 value-position 发射，生成 Rust `if cond { then } else { else }` 表达式，并且不会把分支副作用提前到条件外。
  - generic emitter 支持窄化 value-position short-circuit `&&` / `||` 发射，复用 `emit_condition_expr()` 保留 Rust `&&` / `||` 的 lazy 求值，再 materialize 成 C `int` 0/1。
  - generic emitter 支持一等 scoped `IrStmt::For`，发射为外层 Rust block 加 `while`：loop-init 声明只进入 loop block scope，不泄漏到父级；body 局部声明也不会泄漏到 step。同一层 scoped `ForStmt` body 里的窄化 `continue` 会先发射当前 step 再发射 Rust `continue;`；嵌套循环里的 `continue` 只作用于内层循环。
  - generic emitter 支持窄化 `IrStmt::DoWhile`，发射为 Rust `loop { ... if !(condition) { break; } }`。`DoWhile` body 中的 `continue` 会先执行同一个 loop-exit condition check，再发射 Rust `continue;`，避免直接跳回 loop 顶部导致 C `do-while` condition 被跳过。
  - typed IR 层的旧 crc32 matcher、canned emitter 和 `DeprecatedLegacyCrc32` fallback 已删除；无 globals 的 crc32 IR 会 fail closed，而不是偷偷走模板。
- `crates/c2r-translator/src/translation_route.rs`
  - 定义 typed IR candidate generation 的 route 元数据。
  - `GenericTypedIr` 表示通用 typed IR emitter。
  - `Unsupported` 表示没有 Rust candidate；错误中保留 route metadata 和 fail-closed reason。
- `crates/c2r-translator/src/lib.rs`
  - `try_translate_slice_with_clang_lowered_ir()` 把 `ClangLoweringReport.function_ir` 和 `report.globals` 一起传入 `emit_rust_from_ir_with_globals()`。
  - `write_translation_artifacts()` 在 `clang-lowering-report` feature 下可以写出由 clang-lowered typed IR 驱动的 Rust draft。
  - `clang-lowering-report` artifact 现在包含 `typed_ir_candidate`，记录 `CandidateRouteDecision`、readonly globals 摘要和 `semantic_pass=false` 边界。
  - clang-lowered typed IR 中的 bounded direct identifier call 现在会写入 `plan.call_expressions`；`auto_migrate.py` 会继续映射到 `translation_summary.call_expressions` 和 context-pack `direct_call_edges`，并在 slice spec 声明 external direct callee 时补 `callee_signature_id` / `call_edge_to_callee_binding`。这是 signature/call-edge/source binding provenance，只加固证据一致性，不提升 `semantic_pass`。
  - 旧字符串 translator 中的 crc32 byte-cursor recognizer 和本地 `emit_crc32_byte_cursor_rust()` 已删除；raw string 路径遇到 `*p++` / `size--` 这类未建模副作用会 fail closed，不再生成 `crc32_update_byte()` 模板。FlashDB crc32 的正向 Rust draft 只来自 clang-lowered typed IR + readonly globals + `GenericTypedIr`。
- `validation/tools/auto_migrate.py`
  - 新生成的 `route_decision.candidate_generation.typed_ir` 绑定 clang-lowering-report 中的 typed IR candidate route、readonly globals identity 和 Rust draft provenance。
  - 新生成的 `validation_profile.candidate_generation` 复述同一绑定，但仍保持 `generated_draft_semantic_pass=false`。
  - `typed_ir.status=generated` 且 route 为 `GenericTypedIr` 时作为 typed IR route signal；如果当前 slice 是 scalar-only 且 `token_cost=0`，它走 L0 deterministic candidate route；否则 generated typed IR 仍至少是 L1 signal。`typed_ir.status=unsupported` 会保留原因并作为 L2 repair/baseline route signal。硬拒绝条件、`alias_blocked`、`requires_noalias_contract` 和未知 pointer ownership floor 仍优先；typed IR provenance 会保留在 rationale 中，但不能覆盖这些风险 floor。
- `validation/auto-translation-template/*-schema.json`
  - `candidate_generation` 对旧 route/profile evidence 保持可选，避免破坏 legacy fixtures。
  - 一旦出现 `candidate_generation.typed_ir`，schema 只允许 `GenericTypedIr` / `Unsupported` 两条 typed IR route，并要求 `semantic_pass=false`。
  - 注意：旧 route/profile payload 可以不带 `candidate_generation`，不等于 semantic-pass fixture 可以缺 `c2rust_baseline`、`route_decision`、`validation_profile` refs。
- `validation/tools/validate_auto_translation_evidence.py`
  - 校验 typed IR candidate binding 必须与 clang-lowering-report 一致，并拒绝任何 `semantic_pass=true` 的 candidate 证据。
  - 当 slice spec 声明 external direct callee 时，默认校验路径和 `--require-semantic-pass` 都会把 spec 的 `external_direct_callees` / `signature_ref` / `source_files` 与 plan `translation_summary.call_expressions`、context-pack `direct_call_edges`、`callee_sources`、`signature_bindings` 和逐条 `call_edge_to_callee_binding` 做一致性校验；缺 call site、source hash 漂移、signature shape 漂移、`callee_signature_id` 漂移、binding 漏项或 stub/semantics 边界漂移都会 fail closed。
  - `--require-semantic-pass` 还要求 legacy accepted auto-translation fixtures 持久化 baseline/route/profile refs、cache identities、schema-aware diff metadata 和 negative-diff mutation evidence；测试 helper 临时补字段不能替代落盘 evidence。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - bounded translator 的主要行为契约。
  - 覆盖直接 typed IR 测试、真实 clang AST smoke、真实 FlashDB crc32 parse spec、fail-closed 边界和 rustc smoke 编译。
- `CONTEXT.md`
  - 当前分支的时间顺序交接日志。
  - 恢复开发时优先看最新编号章节。

## 当前核心翻译状态

当前 typed IR candidate generation 层有两类清晰结果：

- `GenericTypedIr`：通用 typed IR emitter，当前真实 FlashDB `fdb_calc_crc32` 在 clang lowering + globals 路径下已经能走到这里并通过 rustc smoke。
- `Unsupported`：没有 Rust candidate，错误中带 fail-closed reason 和 route metadata。

注意：typed IR `CandidateRouteDecision` 只选择候选生成实现，不决定 `semantic_pass`。新 route/profile evidence 会把它绑定进 `route_decision.candidate_generation.typed_ir` 和 `validation_profile.candidate_generation`，作为 provenance；route decision 可以用它区分 scalar-only `token_cost=0` 的 L0 deterministic typed IR 路径、非 scalar 的 L1 generic typed IR 路径，以及 L2 typed IR unsupported repair 路径；存量 route/profile evidence 如果尚未带该字段，schema 仍按 legacy compatibility 接受。真正的接受结论仍由 validation profile、C oracle、Rust replay、schema diff、negative diff、unsafe ledger、final verification 等 gates 决定。legacy compatibility 只覆盖可选字段，不覆盖 semantic-pass refs：`c2rust_baseline`、`route_decision`、`validation_profile`、schema-aware diff 和 negative-diff evidence 必须真实落盘并互相引用一致。

generic typed IR emission 现在覆盖：

- scalar declaration、assignment、return、`if`、`while`、窄化 `do-while`；
- clang-lowered fixed-width integer scalar aliases：`int8_t` / `int16_t` / `int32_t` / `int64_t` / `uint8_t` / `uint16_t` / `uint32_t` / `uint64_t` 现在能作为参数、局部变量和 return 类型进入 typed IR，并发射为 Rust `i8` / `i16` / `i32` / `i64` / `u8` / `u16` / `u32` / `u64`；精确 `signed char` spelling 也可作为 signed 8-bit integer 发射为 Rust `i8`；
- 普通 compound body 和 scoped `ForStmt` init 中的多 `VarDecl` declaration statement，例如 `int a = 1, b = 2;` 和 `for (int i = 0, j = 0; i < limit; i++)`，会展开成连续 typed IR `Decl` 并按源码顺序发射 Rust 局部声明；
- 读取前可证明已有赋值的无初始化标量局部声明，例如 `int tmp; tmp = 7; return tmp;`，会发射为 `let mut tmp: i32; tmp = 7i32; return tmp;`；
- 标量整数二元表达式 `+`、`-`、`*`、`/`、`%`、`&`、`|`、`^`、`<<`、`>>`；
- signed 标量整数 unary minus `-value`；
- clang-lowered simple scalar compound assignment family：`+=`、`-=`、`*=`、`/=`、`%=`、`&=`、`|=`、`^=`、`<<=`、`>>=` 覆盖 standalone statement 和 simple `ForStmt` step 中的 simple scalar variable target；当 clang 证明 target/result 是同一个受支持整数类型、compute lhs/result 是同一个受支持整数类型时，compute type 可以不同于 target type，并通过显式 cast lowering，例如 `value = (((value as i32) + 1i32) as u8);`；
- clang-preserved value-position integer implicit casts：覆盖 declaration initializer、assignment RHS 和 return value，例如 `uint32_t value = 1; value = 2; return 3;` 可在 source/target 都是受支持整数类型时 lowering 成 typed IR cast，并发射 `(1i32 as u32)`、`(2i32 as u32)`、`(3i32 as u32)`；
- clang-preserved binary operand integral casts：普通二元整数运算只在 clang 已插入 `IntegralCast` / `IntegralPromotion` 且 cast 后 lhs/rhs/result 类型严格对齐时发射，例如 `uint32_t add_byte(uint32_t acc, uint8_t byte) { return acc + byte; } -> return (acc + (byte as u32));`，以及 `signed char value + 1 -> ((value as i32) + 1i32)`；
- comparison expression 的条件位置和窄 value-position：`if` / `while` 条件继续发 Rust bool condition；`return x > 0`、`out = x == y`、`int ok = x != 0` 等 value-position 生成 C `int` 0/1 materialization；
- logical not `!expr` 的条件位置和窄 value-position：`if (!value)` / `while (!value)` 生成 `value == 0`，`!(value > 0)` 生成反转后的 comparison condition；`return !value`、assignment RHS 和 declaration initializer 等 value-position 生成 C `int` 0/1 materialization，例如 `if value == 0 { 1i32 } else { 0i32 }`；
- short-circuit `&&` / `||` 的条件位置和窄 value-position：`if (left && right)` / `while (left || right)` 生成 Rust bool 条件；`return left && right`、`out = left || right` 和 `int out = left && (right > 0)` materialize 成 C `int` 0/1；左右操作数递归复用当前 `emit_condition_expr()` 支持的整数 truthiness、comparison、logical-not、readonly deref 和 bounded offset-deref 子集；
- 普通 clang `ConditionalOperator` / `?:` 的纯整数 value-position：`return flag ? left : right`、`out = flag ? value : fallback`、`int out = flag ? left : right` 会 lowering 成 lazy typed IR `IrExpr::Conditional`，并发射 Rust `if flag != 0 { ... } else { ... }` 表达式；clang 已保留的分支整型 cast 会继续保留，例如 `uint32_t choose(uint32_t flag, uint32_t value) { return flag ? value : 2; }` 的 else arm 会发射 `(2i32 as u32)`；
- 窄化 scoped `ForStmt`：`for (int i = 0; i < limit; i++) { total = total + i; }`、`for (int i = 0; i < limit; ++i) { total = total + i; }` 和 `for (int i = 0, j = 0; i < limit; i++) { total = total + i + j; }` lowering 成一等 `IrStmt::For`，发射为 Rust block + `while` 形态；多个 init 声明按源码顺序在 loop block 内发射，不泄漏到 loop block 外，body 内声明不泄漏到 step；step-position 的简单标量 `++i` / `--i` 只按 statement side effect lowering 成 `i = i +/- 1`，不表示 value-position inc/dec 已支持；
- 窄化 `DoStmt` / `do-while`：真实 clang `DoStmt` 现在 lowering 成 `IrStmt::DoWhile`，发射为 Rust `loop` 加尾部 condition break check；body 至少执行一次，condition 仍复用当前 `emit_condition_expr()` 子集；
- loop-body `break`：真实 clang `BreakStmt` 现在 lowering 成 `IrStmt::Break`，只在 `while` / `do-while` / scoped `ForStmt` body 内发射 Rust `break;`；顶层 `break` 和非 loop 上下文继续 fail closed；
- 窄化 loop-body `continue`：真实 clang `ContinueStmt` 现在 lowering 成 `IrStmt::Continue`；`while` body 发射 Rust `continue;`，`do-while` body 会先检查同一个 loop condition 再 `continue;`，scoped `ForStmt` body 会先发射简单 step 再发射 Rust `continue;`，嵌套循环里的 `continue` 不会误执行外层 loop 的 step/condition shim，顶层或非 loop 上下文的 `continue` 继续 fail closed；
- 来自 clang AST 的 initialized scalar local；
- 来自 clang AST 的无大括号 `if` / `while` body；
- readonly integer pointer parameter 到 Rust slice，例如 `const uint32_t *table -> table: &[u32]`；
- readonly integer pointer parameter 的 null-presence check，例如 `const int *values; return values != NULL; -> values: Option<&[i32]>` 和 `values.is_some()`；nullable 参数必须只出现在直接 `== NULL` / `!= NULL` comparison 中；
- readonly integer pointer parameter 的 dereference read，例如 `const uint8_t *p; return *p; -> p: &[u8]` 和 `return p[0usize];`，以及 bounded offset-deref read，例如 `return *(p+i);` / `return *(i+p); -> return p[i as usize];`；这些 read 也可以作为普通标量 read 参与 comparison/logical-not candidate generation，例如 `*p == 0`、`*(p+i) == 0`、`!*p` 和 `!*(p+i)`；
- mutable integer pointer output write：`int *out` 只有在作为写目标出现时发射为 `out: &mut [i32]`，并支持 `*out = value; -> out[0usize] = value;`、`out[i] = value; -> out[i as usize] = value;`、`*(out+i) = value; -> out[i as usize] = value;`；当前只覆盖函数参数上的整数元素写入，不覆盖 mutable pointer read、复合写入、复杂 offset、nullable pointer、pointer escape、多指针 alias/noalias 证明或 semantic acceptance；
- `static const` readonly integer array initializer 到 Rust `const`，例如 `crc32_table[] -> const CRC32_TABLE: [u32; 256]`；
- clang-lowered typed IR 的局部固定长度整数数组字面量、下标读取和元素写入，例如 `uint32_t table[3] = {1,2,3}; table[i] = value; return table[i]; -> let mut table: [u32; 3] = ...; table[i as usize] = value;`；只支持 clang AST 中已规整为纯整数字面量/cast 的 initializer 元素，且写入目标必须是已声明的局部固定长度整数数组。partial initializer zero-fill、nested array、struct array、非 literal 或有副作用的 initializer、VLA/incomplete array、readonly global array 写入、const pointer slice 写入和 array-to-pointer decay 仍 fail closed；
- 当已经证明存在 `const uint8_t *p` byte cursor 和 byte read 时，把 `const void *buf` 翻译成 `&[u8]`；
- 通过 prelude temporary 支持嵌套 byte cursor read，例如 `(uint32_t)*p++`；
- assignment RHS prelude，覆盖 `crc = table[(crc ^ (uint32_t)*p++) & 0xff] ^ (crc >> 8);`；
- bounded direct identifier call：只支持 clang `referencedDecl.kind=FunctionDecl` 的直接函数名 callee，覆盖 call statement、decl init、assignment RHS 和 return value，并把 callee、arguments、source expression、statement context 写入 `call_expressions` 证据；如果 slice spec 声明 external direct callee，validator 还要求 plan/context/binding 的每个 call site 和 signature 逐条一致；嵌套 call、函数指针 callee、缺少 `FunctionDecl` 证明的 callee、condition 表达式全树中的 call、inc/dec 或 deref 参数继续 fail closed；
- 窄化的 `size_t` postfix-decrement while condition，把 `while (size--)` lowering 成保留 postfix side effect 的 Rust `loop`。

仍未完成：

- 当前只是候选生成链路能生成并编译 Rust，并且 route/profile 已绑定 candidate provenance；raw string crc32 byte-cursor 输入现在保持 fail-closed。真实 FlashDB slice 的 semantic acceptance 仍需要完整 validation gates。
- fixed-width integer alias 和精确 `signed char` coverage 只是 clang type skeleton / typed IR candidate generation。`short` / `long long` 这类其他目标相关 spelling、plain `char`、plain `long`、target ABI 宽度推断、完整 integer promotion/usual scalar conversions、以及 semantic acceptance 仍未建模。
- multi `VarDecl` expansion 只覆盖普通 compound body 和 scoped `ForStmt` init 中每个 declarator 本身已可 lowering 的场景；unsupported type/initializer、VLA/incomplete array、init marker 无 child、多个 initializer child、重复符号、复杂 init/step 和 semantic acceptance 仍 fail closed。
- 无初始化标量局部声明仍只是 candidate generation，并要求保守的 assignment-before-read 证明。读取前未赋值、首次赋值读取自身、只在 loop 或单侧 branch 中赋值、无 initializer 数组、pointer/record/function 声明、address-taken initialization、间接写入、alias write 和 semantic acceptance 仍 fail closed。
- `*`、`/`、`%` 只表示窄化标量整数 candidate generation。不能据此声明支持除零、全部 C 算术、浮点算术、完整 usual arithmetic conversions、overflow/UB parity 或指针算术；除法/取模只有在 divisor 非零由 literal、fixture 输入域或 slice contract 明确约束时，才可进入 semantic acceptance 讨论。
- bitwise OR / left shift 只表示窄化标量整数 candidate generation。当前 `|` 要求左右 operand 和 result 是同一个标量整数类型，`<<` 沿用 shift 规则要求 lhs/result 类型一致；它不声明完整 C 位运算/位移语义、usual arithmetic conversions、无效 shift count、signed shift/overflow UB parity、指针算术或 semantic acceptance。
- signed unary minus 也只是窄化 candidate generation。它要求 operand/result 是同一个 signed integer scalar type；unsigned 或 wrapping 取负、浮点取负、指针算术、复合 `-=`、以及 `-2147483648` 这类 literal 边界仍未建模，必须继续 fail closed。
- compound assignment family 只是 clang-lowered candidate generation。它只覆盖 standalone statement 和 simple `ForStmt` step 中的 simple scalar variable target；窄化 clang-proven integer promotion/truncation 只在 target/result 一致、compute lhs/result 一致且所有类型都是受支持整数时可过。`*p += y`、`a[i] += y`、`s.f += y`、`p->f += y`、value-position `(x += y)`、condition/call argument 中的 compound assignment、未被该 guard 证明的 promotion/truncation、pointer arithmetic、float、volatile、复杂 RHS side effect 和 semantic acceptance 继续 fail closed。
- value-position 和 binary operand implicit cast preservation 只是 clang-lowered candidate generation。它只保留 declaration initializer、assignment RHS、return value 或普通二元 operand 中的 clang `IntegralCast` / `IntegralPromotion` 节点，typed IR emitter 仍要求 source/target 都是受支持整数类型，并且二元运算 cast 后 lhs/rhs/result 严格同型；函数指针 decay、现有显式 byte-cursor 处理之外的 pointer cast、float cast、隐藏副作用转换、cast 结果仍与语句边界类型不匹配的情况，以及完整 usual scalar conversions 继续 fail closed。
- comparison expression 只是 candidate generation，条件位置和窄 value-position 都保持 `semantic_pass=false`。当前覆盖窄化标量整数比较、C `int` 0/1 materialization、comparison operand 上 source/target 都是可发射整数类型且 cast 后两侧类型完全一致的 integral cast、readonly integer pointer 参数的 null presence check、readonly direct deref read operand，以及 bounded readonly offset-deref read operand；除 bounded readonly `*(p+i)` read 外的任意 pointer arithmetic、任意 pointer comparison、float comparison、未由 clang-preserved 或显式整数 cast 对齐的 mixed-width/unsigned conversions、call/inc/dec side-effect operands、pointer truthiness、null check 后继续 deref/index 使用、完整 usual scalar conversions 和 semantic acceptance 继续 fail closed。
- logical not 只是 candidate generation，条件位置和窄 value-position 都保持 `semantic_pass=false`。当前只覆盖整数零比较、反转 comparison condition、readonly direct deref read operand、bounded readonly offset-deref read operand，以及 C `int` 0/1 结果 materialization；它不是完整 C unary `!`，operand 含 call、inc/dec、未建模 deref side effect、pointer truthiness、窄化 readonly pointer-parameter presence 表面之外的 pointer null check、float truthiness、unsupported type 或完整 usual scalar conversions 时继续 fail closed。
- short-circuit `&&` / `||` 只是 candidate generation，覆盖条件位置和窄 value-position，且结果类型必须是 C `int`。value-position 只覆盖 return value、assignment RHS 和 declaration initializer，并用 Rust `&&` / `||` 保留 lazy 求值后 materialize C `int` 0/1；operand 含 call/inc/dec/side effect、pointer truthiness、float truthiness、unsupported type 或需要完整 usual scalar conversions 时继续 fail closed。
- conditional `?:` 只是 candidate generation，目前只覆盖纯整数 value-position。condition-position `if (a ? b : c)` / `while (a ? b : c)`、expression statement、GNU omitted-middle `a ?: b`、then/else 分支中的 call/inc/dec/post-increment/assignment/comma 副作用、pointer 或 floating-point 结果、pointer truthiness、aggregate 结果、未建模 usual scalar conversions 和 semantic acceptance 继续 fail closed。
- structured loop candidate generation 仍是窄化子集。`ForStmt` 只覆盖简单 scalar declaration/assignment init（含多个简单 `VarDecl` declarator）、condition、assignment/compound-assignment/postfix-or-prefix inc-dec step 和现有 statement body 子集；`DoWhile` 只覆盖 body 子集和当前 condition emitter 能证明的 condition。`break` 只作为直接 loop exit 发射；`continue` 只支持 loop body：`while` body 直接发射 Rust `continue;`，`do-while` body 先检查 condition 再 `continue;`，同一层 scoped `ForStmt` body 会先发射当前 step 再发射 Rust `continue;`。`goto` / `switch`、condition variable slot、空 `ForStmt` condition/step、condition 中 call/inc/dec/side effect、复杂 init/step、value-position inc/dec、非 scalar step、完整 C loop control-flow semantics 和 semantic acceptance 继续 fail closed。
- mutable pointer write 只是窄化 candidate generation：当前只把函数参数 `T *out` 上的直接 `*out`、下标 `out[i]`、简单加法 offset `*(out+i)` / `*(i+out)` 写入发射为 `&mut [T]` slice assignment。`const T *` 写入、mutable pointer read、`out[i+j]` / `*(out+i+1)` / `*(out+f())`、compound/update 写、pointer 自身递增、返回/转发 pointer、多 mutable pointer alias/noalias 证明、nullable pointer 和 semantic acceptance 仍 fail closed。
- 复杂函数指针、未建模 alias write、volatile/硬件寄存器、宏副作用和跨线程/中断语义仍应 fail closed 或进入更高路线。

## 下一步实现切口

1. 继续用红测优先扩展 generic typed IR 覆盖；当前更适合的后续切口是 nested pure direct calls、standalone typed clang inc/dec statement、struct/alias memory model 设计，或继续设计 `switch` / `goto` 的控制流语义。multi `VarDecl` body expansion、`ForStmt` init 多声明、assignment-before-read 无初始化标量局部声明、fixed-width integer aliases、精确 `signed char`、binary operand integral cast preservation、condition/value-position `&&` / `||`、包含窄化 clang-proven promotion/truncation 的 simple scalar compound assignment family、value-position integer implicit cast preservation、纯整数 value-position `ConditionalOperator` / `?:`、窄化 scoped `ForStmt`、step-position prefix inc/dec、窄化 `do-while`、loop-body `break`、窄化 loop-body `continue`、readonly `*(p+i)` read 和 mutable pointer output write 已有 direct/clang-lowered/real-clang smoke 覆盖；bounded readonly `*(p+i)` read、mutable pointer write 的 fail-closed offset/const 边界、lazy `?:` 分支语义、short-circuit lazy 求值、for-loop scope 边界、`ForStmt` continue-step 顺序、step-position inc/dec 边界和 `DoWhile` continue-condition check 要继续保留 real-clang 与 fail-closed 边界覆盖；除这些窄切片外的任意 pointer arithmetic、任意 pointer comparison、float comparison、未建模 mixed-width conversions、side-effect operands 和 semantic acceptance 仍要 fail closed。
2. 对真实 FlashDB crc32 跑完整 C/Rust oracle、negative diff、unsafe ledger 和 final verification。
3. 保留 raw string crc32 byte-cursor fail-closed 回归测试，避免 `crc32_update_byte()` 模板或 `crc32-byte-cursor-loop` rule 被重新引入。
