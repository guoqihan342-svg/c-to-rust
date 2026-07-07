## 82. 2026-06-27 typed IR local fixed array index read

本轮继续按多线程审查下一步切口。三个只读线程结论：

- direct-call signature evidence 是重要 soundness 切口，但需要重新设计 callee signature 进入 `ClangExprSkeleton::Call` / `IrExpr::Call` / evidence 的 contract。
- simple struct field reads/writes 价值高，但会牵出 `MemberExpr`、record layout、Rust struct 定义、`&Point` / `&mut Point` 边界和 assignment target 泛化，切口偏大。
- router risk floor 能防止 `GenericTypedIr` 把 alias-blocked pointer slice 误降到 L1，但它是路由正确性，不直接扩大 typed IR 可翻译 C 子集。

本轮主线选了更小的核心翻译切口：typed IR 层的局部固定长度整数数组字面量 + 只读下标读取。它复用现有 `IrTypeKind::Array` 和 `IrExpr::Index`，先不接真实 clang `InitListExpr`。

核心改动：

- `crates/c2r-translator/src/typed_ir.rs`
  - 新增 `IrExpr::ArrayLiteral { elements, ty, source_span }`。
  - `IrStmt::Decl` 现在允许固定长度整数数组声明使用数组字面量初始化，生成 Rust `let table: [u32; 3] = [1u32, 2u32, 3u32];`。
  - `emit_index_expr()` / `emit_index_expr_with_emitted_index()` 现在除了 readonly global array 和 readonly pointer slice，也接受已声明的 local fixed integer array 作为 index base。
  - 数组字面量保持窄化：只支持声明 initializer 位置；长度未知、元素数量不匹配、非整数元素或在 call/普通表达式位置使用都会 fail closed。

- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 `typed_ir_emits_local_fixed_array_index_read`。
  - 红测阶段先失败于 `IrExpr::ArrayLiteral` variant 不存在；实现后通过，并用 `rustc` smoke 验证生成片段可编译。
  - 顺手把 `without_implicit_cast()` / `repeated_c_u32_initializer()` 的 cfg 收窄到 clang frontend 相关 feature，避免 `typed-ir` 单独测试产生 dead_code warning。

- `docs/c2rust-migration-agent/core-translation-architecture.md`
- `docs/c2rust-migration-agent/core-translation-architecture.en.md`
  - 双语同步 generic typed IR coverage：local fixed integer arrays。

本轮已跑过的验证：

```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_emits_local_fixed_array_index_read -- --nocapture
cargo fmt --manifest-path crates/c2r-translator/Cargo.toml
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir
$env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend
```

当前边界：

- 这只是 typed IR -> Rust emitter 能力；真实 C `InitListExpr` / local array lowering 还没接到 clang frontend。
- local array 当前只支持固定长度整数数组、声明时初始化、只读 index。数组元素写入、指针衰减、变长数组、struct array 仍应 fail closed。
- 下一步可以在两个方向继续：接 clang `InitListExpr` 到 `ArrayLiteral`，或按并行线程建议补 direct-call callee signature evidence / router risk floor。

## 83. 2026-06-27 clang local array InitListExpr and typed IR route risk floor

本轮按多智能体并行继续。三个只读线程结论：

- `InitListExpr -> ArrayLiteral` 是上一节 typed IR local array 能力的最小前端接线，应立即做，并补真实 clang AST smoke。
- router risk floor 有实际问题：`GenericTypedIr` generated 当前会先返回 L1，绕过 pointer graph 中的 alias blocked / requires-noalias 风险。
- direct-call callee signature evidence 是下一步 soundness hardening，建议排在 InitListExpr 之后，不要拖到 broad direct-call 推广之后。

本轮主线完成两件事。

1. clang frontend 现在支持局部固定长度整数数组 initializer。

- `crates/c2r-translator/src/clang_frontend.rs`
  - `ClangExprSkeleton` 新增 `ArrayLiteral { elements, ty }`。
  - `expr_skeleton_from_ast_with_options()` 新增 `InitListExpr` 分支。
  - 新增 `init_list_expr_skeleton_from_ast()`，只接受一维 fixed-size integer array，且 initializer element count 必须等于数组长度。
  - initializer 元素只允许纯 `IntegerLiteral` 或整型 cast 包裹的 `IntegerLiteral`；变量、call、binary、inc/dec、deref 等非 literal 或副作用表达式 fail closed。
  - initializer 元素保留 `IntegralCast` / `IntegralPromotion`，避免真实 clang 把 `{1}` 初始化 `uint32_t[]` 时丢掉 cast。
  - `ArrayLiteral` 作为 call argument 继续 fail closed。
  - `lower_expr()` 把 `ClangExprSkeleton::ArrayLiteral` lowering 成 `IrExpr::ArrayLiteral`。

- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 `typed_ir_emits_local_fixed_array_index_read_from_clang_lowered_ir`，覆盖 `ClangFunctionSkeleton -> IrFunction -> Rust`。
  - 新增 gated real clang smoke `clang_ast_dump_emits_local_fixed_array_initializer_when_enabled`，验证真实 C：
    `uint32_t table[3] = {1U, 2U, 3U}; return table[i];`
    能从 clang AST lowering 到 `IrExpr::ArrayLiteral`，并生成可 rustc 编译的 Rust。
  - code review 后补 `decl_stmt_skeleton_from_ast_rejects_fixed_array_initializer_call_element` 和 gated real clang smoke `clang_ast_dump_rejects_local_array_initializer_call_when_enabled`，避免 array initializer 里带 direct call 时按 Rust 数组 literal 发射。

2. route decision 现在有最小 alias risk floor。

- `validation/tools/auto_migrate.py`
  - `route_level()` 不再让 typed IR generated signal 提前覆盖 pointer graph risk。
  - 新增 `alias_route_floor()`。
  - `alias_contract.decision == "blocked"` 时保持 L3。
  - `requires_noalias_contract` 或 `unknown_alias` risk 时保持 L2。
  - pointer ownership role 为 `unknown` 时保持 L2。
  - `GenericTypedIr` provenance 仍写入 rationale，但不能把上述风险降到 L1。

- `validation/tools/test_auto_migrate.py`
  - 新增 `test_generated_typed_ir_candidate_with_alias_risk_routes_l2_not_l1`。
  - 新增 `test_generated_typed_ir_candidate_does_not_override_blocked_alias_route`。

- 双语文档已同步：
  - `docs/c2rust-migration-agent/core-translation-architecture.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.en.md`
  - `docs/c2rust-migration-agent/README.md`
  - `docs/c2rust-migration-agent/README.en.md`
  - `docs/superpowers/specs/2026-06-27-candidate-route-p0-design.md`
  - `docs/superpowers/specs/2026-06-27-candidate-route-p0-design.en.md`

已跑过的聚焦验证：

```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend decl_stmt_skeleton_from_ast_maps_fixed_array_initializer_list -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend typed_ir_emits_local_fixed_array_index_read_from_clang_lowered_ir -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend decl_stmt_skeleton_from_ast_rejects_fixed_array_initializer_count_mismatch -- --nocapture
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend clang_ast_dump_emits_local_fixed_array_initializer_when_enabled -- --nocapture
 $env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend clang_ast_dump_rejects_local_array_initializer_call_when_enabled -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend
python -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_generated_typed_ir_candidate_with_alias_risk_routes_l2_not_l1 validation.tools.test_auto_migrate.AutoMigrateTests.test_generated_typed_ir_candidate_does_not_override_blocked_alias_route validation.tools.test_auto_migrate.AutoMigrateTests.test_generated_typed_ir_candidate_is_l1_route_signal validation.tools.test_auto_migrate.AutoMigrateTests.test_unsupported_typed_ir_candidate_preserves_reason_and_routes_l2
```

本轮最终验证已跑：

```powershell
cargo fmt --manifest-path crates/c2r-translator/Cargo.toml
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report
python -m unittest validation.tools.test_auto_migrate validation.tools.test_validate_auto_translation_evidence
openspec validate --all --strict
git diff --check -- CONTEXT.md crates/c2r-translator/src/clang_frontend.rs crates/c2r-translator/tests/bounded_translation.rs validation/tools/auto_migrate.py validation/tools/test_auto_migrate.py docs/c2rust-migration-agent/README.md docs/c2rust-migration-agent/README.en.md docs/c2rust-migration-agent/core-translation-architecture.md docs/c2rust-migration-agent/core-translation-architecture.en.md docs/superpowers/specs/2026-06-27-candidate-route-p0-design.md docs/superpowers/specs/2026-06-27-candidate-route-p0-design.en.md
```

当前边界：

- 可以说：真实 clang AST 中的局部固定长度整数数组 initializer 已能进入 typed IR，并生成可编译 Rust。
- 不应说：已支持 C 数组完整语义。当前只支持 clang AST 中已规整为纯整数字面量/cast 的 initializer 元素；partial initializer zero-fill、nested array、struct array、非 literal 或有副作用 initializer、VLA/incomplete array、local array write、array-to-pointer decay 仍 fail closed。
- 可以说：`GenericTypedIr` 不再覆盖 alias blocked / requires-noalias 风险 floor。
- 不应说：完整 L0-L4 router 已完成；当前只是 typed IR route signal 上方的最小 alias/ownership floor。

English mirror summary:

- Local fixed-size integer-array `InitListExpr` now lowers to `IrExpr::ArrayLiteral` and reaches compilable Rust through the generic typed IR emitter.
- The route decision now keeps `GenericTypedIr` provenance but does not let it override alias-blocked, requires-noalias, unknown-alias, or unknown pointer-ownership floors.
- Next soundness cut: direct-call callee signature evidence binding across plan/context/validator.

## 84. 2026-06-27 clang-lowered direct-call evidence

本轮按多智能体并行继续 direct-call soundness 切口。三个只读线程结论：

- Rust translator 侧已经能从真实 clang `CallExpr` 走到 `ClangExprSkeleton::Call -> IrExpr::Call -> emit_call_expr()`，但 clang-lowered typed IR 路径此前没有把 `IrExpr::Call` 写入 `TranslationPlan.call_expressions`。
- validation 侧已有 `external_direct_callees` / `signature_ref` / `callee_signature_id` / context-pack binding 机制；它只消费 plan 里的 `call_expressions`，不需要新增字段。
- 文档需要同步核心架构、README、candidate route P0 设计和本 `CONTEXT.md`，并继续避免触碰预存 dirty `validation/evidence/**`。

核心改动：

- `crates/c2r-translator/src/lib.rs`
  - `record_clang_lowered_ir_evidence()` 现在会调用新的 IR call evidence collector。
  - 新增递归扫描 `IrStmt` / `IrExpr` 的 helper，把 clang-lowered typed IR 中的 `IrExpr::Call` 转成现有 `CallExpressionEvidence { callee, arguments, source_expression, statement_context }` 形状。
  - 支持 decl initializer、assignment RHS、return value、expr statement，以及 if/while body 内的递归遍历；condition 中的 call 仍属于当前 typed IR emitter 的 fail-closed 边界，不作为成功路径 evidence 宣称。
  - 只要记录到 direct call evidence，就同步写入 `bounded-call-expression` rule id，保持与旧 bounded string 路径的 evidence 语义一致。
  - 新增 crate 内部 TDD 单测 `clang_lowered_ir_records_direct_call_expression_evidence`。红测先失败于 `call_expressions.len() == 0`，实现后通过；随后补 rule id 断言，先失败再通过。
  - code review 后补 `clang_lowered_ir_preserves_repeated_direct_call_sites_in_same_context` 和 `clang_lowered_ir_does_not_record_condition_call_as_success_evidence`，确保重复 call site 不被文本去重吞掉，同时 condition call 不被当成成功路径 evidence。
- 双语文档已同步：
  - `docs/c2rust-migration-agent/core-translation-architecture.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.en.md`
  - `docs/c2rust-migration-agent/README.md`
  - `docs/c2rust-migration-agent/README.en.md`
  - `docs/superpowers/specs/2026-06-27-candidate-route-p0-design.md`
  - `docs/superpowers/specs/2026-06-27-candidate-route-p0-design.en.md`

本轮已跑过的聚焦验证：

```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_lowered_ir_records_direct_call_expression_evidence -- --nocapture
cargo fmt --manifest-path crates/c2r-translator/Cargo.toml
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report direct_identifier_call -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report translates_direct_call_expressions_and_records_callee_evidence -- --nocapture
python -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_call_expression_evidence_flows_through_auto_migrate validation.tools.test_auto_migrate.AutoMigrateTests.test_declared_external_callee_context_allows_helper_rust_check
```

当前边界：

- 可以说：clang-lowered typed IR direct calls 现在会进入现有 plan `call_expressions`，后续 `auto_migrate.py` 可继续生成 `translation_summary.call_expressions`、context-pack `direct_call_edges`、外部 callee signature binding。
- 不应说：完整 direct-call signature system 已完成。当前只是把 typed IR call provenance 接入既有 evidence 通路；semantic acceptance 仍由 validation gates 决定。
- 仍不要 stage/revert/格式化 `validation/evidence/**` 中的预存脏文件。

English mirror summary:

- Clang-lowered typed IR direct calls now populate the existing `TranslationPlan.call_expressions` evidence shape.
- The existing validation tooling can map those calls into `translation_summary.call_expressions`, context-pack `direct_call_edges`, and external-callee signature bindings when the slice spec declares them.
- This is provenance only; `semantic_pass` remains owned by the validation pipeline.

## 85. 2026-06-27 local fixed array index assignment

本轮继续按多智能体并行推进核心翻译能力。五个只读线程给出的排序里，direct-call signature binding 是下一步 soundness 切口，标量减法是更小的 C 子集扩展；本轮主线选择了文档中明确仍 fail-closed 的局部数组元素写入，因为它直接补齐已有 `InitListExpr -> ArrayLiteral -> Index read` 通路的下一步。

核心改动：

- `crates/c2r-translator/src/typed_ir.rs`
  - `EmitContext` 现在保存 `assigned_vars`，供参数和局部声明统一判断 `mut`。
  - `IrStmt::Assign` 的 target 发射拆为 `emit_assignment_target()`；`Var` 保持原逻辑，`Index` 只允许“已声明的 local fixed integer array + integer index”。
  - 新增 `emit_local_array_index_assignment_target()`，显式拒绝 readonly global array 写入、const pointer slice 写入、非数组 base、非整数 index 和元素类型不匹配。
  - `collect_assigned_vars_from_body()` 现在会把 `Assign target = Index(base Var, ...)` 的 base 计入 assigned vars，因此 `uint32_t table[3]...; table[i] = value;` 会发射 `let mut table: [u32; 3] = ...;`。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 `typed_ir_emits_local_fixed_array_index_assignment`。红测先失败于 `stmt[1].assign target must be Var`，实现后通过并用 rustc smoke 验证。
  - 新增 `typed_ir_emits_local_fixed_array_index_assignment_from_clang_lowered_ir`，证明 `ClangFunctionSkeleton -> IrFunction -> Rust` 不需要前端新增节点即可走通。
  - 新增 gated real clang smoke `clang_ast_dump_emits_local_fixed_array_index_assignment_when_enabled`，验证真实 C：
    `uint32_t replace_local_table_slot(size_t i, uint32_t value) { uint32_t table[3] = {1U, 2U, 3U}; table[i] = value; return table[i]; }`
  - 新增 fail-closed 负例 `typed_ir_rejects_readonly_global_array_index_assignment` 和 `typed_ir_rejects_const_pointer_index_assignment`，避免误放开 readonly global 或 const pointer slice 写入。
  - 更新旧的复杂左值负例断言，继续保证 while/if 中非 `Var` / local fixed array `Index` target 仍 fail closed。
- 双语文档已同步：
  - `docs/c2rust-migration-agent/core-translation-architecture.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.en.md`
  - `docs/c2rust-migration-agent/README.md`
  - `docs/c2rust-migration-agent/README.en.md`
  - `docs/superpowers/specs/2026-06-27-candidate-route-p0-design.md`
  - `docs/superpowers/specs/2026-06-27-candidate-route-p0-design.en.md`

本轮已跑过的聚焦验证：

```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_emits_local_fixed_array_index_assignment -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend typed_ir_emits_local_fixed_array_index_assignment -- --nocapture
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend clang_ast_dump_emits_local_fixed_array_index_assignment_when_enabled -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir index_assignment -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir non_var_assignment_target -- --nocapture
```

当前边界：

- 可以说：真实 clang AST 中的局部固定长度整数数组 initializer、下标读取和元素写入现在能进入 typed IR，并通过 generic typed IR emitter 生成可编译 Rust。
- 不应说：已支持 C 数组完整语义。当前写入目标只允许已声明的局部固定长度整数数组；readonly global array 写入、const pointer slice 写入、array-to-pointer decay、VLA/incomplete array、nested/struct array 和副作用 initializer 仍 fail closed。
- 不应说：`GenericTypedIr` candidate 表示 semantic acceptance；它仍只是候选生成 provenance，接受结论由 validation gates 决定。
- 仍不要 stage/revert/格式化 `validation/evidence/**` 中的预存脏文件。

English mirror summary:

- Local fixed-size integer-array initializer, index reads, and element writes now flow from real clang AST through typed IR into compilable Rust.
- Writes are deliberately narrow: only declared local fixed-size integer arrays are accepted. Readonly global writes, const pointer-slice writes, array-to-pointer decay, VLAs/incomplete arrays, nested/struct arrays, and side-effecting initializers still fail closed.
- This remains candidate generation only; semantic acceptance belongs to the validation gates.
- Recommended next cut remains external direct-callee signature/call-site binding hardening across plan, context pack, and validator, or the small scalar subtraction `-` expansion if prioritizing C subset breadth.

## 86. 2026-06-27 external direct-callee binding validator hardening

本轮按用户要求继续多智能体并行推进。四个只读线程结论：

- validator 原先只做 callee name 级别检查，缺少逐 call-site、source binding 和 call-edge enrichment 校验。
- `auto_migrate.py` 产物里 plan 使用 `callee_signature_id`，context binding 使用 `signature_ref`，这是当前显式兼容契约。
- 文档必须写清：这是 evidence integrity / provenance hardening，不是 external callee semantic acceptance。
- 预存 `validation/evidence/**` 仍是脏文件，本轮不 stage、不 revert。

核心改动：

- `validation/tools/validate_auto_translation_evidence.py`
  - 默认 validator 路径现在也会在 slice spec 声明 `external_direct_callees` 时调用 external direct-callee context 校验；不再只挂在 `--require-semantic-pass`。
  - external direct-callee 校验现在把 spec `signature_ref` / `source_files` 与 plan `translation_summary.call_expressions`、context-pack `direct_call_edges`、`callee_sources`、`signature_bindings`、`call_edge_to_callee_binding` 做一致性校验。
  - 新增 source binding 校验：source path/sha、source_ref、definition_status 漂移会 fail closed。
  - 新增 call-site metadata 校验：plan/context direct call edge 必须保持 `callee_scope=external_direct_callee`、`stub_status=compile_only`、`callee_source_ref`、`definition_status` 和 expected signature 一致。
  - signature binding 现在要求每个 declared callee 恰好一个 binding，避免重复 binding 被静默覆盖。
  - code review 后补 recorded/blocked 分流：unsupported external callee 的 blocked evidence 不再被默认 validator 误杀；blocked callee 现在校验 `external_direct_callee_blocks`、blocked call edge metadata 和 `stub_kind=none` / `semantics_verified=false`。
- `validation/tools/test_validate_auto_translation_evidence.py`
  - 新增红绿测试：默认 validator 路径缺 external callee binding 必须失败。
  - 新增红绿测试：`callee_sources` sha 漂移必须失败。
  - 新增红绿测试：call-site enrichment 字段漂移必须失败。
  - code review 后补红绿测试：blocked external callee 必须允许通过 fail-closed evidence；plan/context direct call edge 单边漂移必须失败。
  - helper 里的 plan/context call edge 改为深拷贝，避免测试 mutation 共享对象掩盖 drift。
  - 保留并扩展上一轮红绿测试：缺 call-site binding、signature shape 漂移、signature binding 漂移都必须失败。
- `validation/tools/test_auto_migrate.py`
  - 正向断言 external direct callee descriptor、call expressions、context direct edges 和 call-edge bindings 的字段契约。
- 双语文档已同步：
  - `docs/c2rust-migration-agent/README.md`
  - `docs/c2rust-migration-agent/README.en.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.en.md`
  - `docs/superpowers/specs/2026-06-27-candidate-route-p0-design.md`
  - `docs/superpowers/specs/2026-06-27-candidate-route-p0-design.en.md`

TDD 红灯已确认：

```powershell
python -B -m unittest validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_rejects_default_validation_missing_external_callee_context_binding validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_external_direct_callee_context_rejects_callee_source_drift validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_external_direct_callee_context_rejects_call_site_enrichment_drift
```

实现后已跑验证：

```powershell
python -B -m unittest validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_rejects_default_validation_missing_external_callee_context_binding validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_external_direct_callee_context_rejects_callee_source_drift validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_external_direct_callee_context_rejects_call_site_enrichment_drift
python -B -m unittest validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_external_direct_callee_context_rejects_context_direct_call_edge_drift validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_external_direct_callee_context_allows_blocked_external_callee validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_external_direct_callee_context_requires_every_call_site_binding validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_external_direct_callee_context_rejects_signature_shape_drift validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_external_direct_callee_context_rejects_signature_binding_drift validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_external_direct_callee_context_rejects_callee_source_drift validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_external_direct_callee_context_rejects_call_site_enrichment_drift validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_rejects_default_validation_missing_external_callee_context_binding validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_rejects_semantic_pass_missing_external_callee_context_binding
python -B -m unittest validation.tools.test_validate_auto_translation_evidence validation.tools.test_auto_migrate
openspec validate --all --strict
git diff --check -- CONTEXT.md validation/tools/validate_auto_translation_evidence.py validation/tools/test_validate_auto_translation_evidence.py validation/tools/test_auto_migrate.py docs/c2rust-migration-agent/README.md docs/c2rust-migration-agent/README.en.md docs/c2rust-migration-agent/core-translation-architecture.md docs/c2rust-migration-agent/core-translation-architecture.en.md docs/superpowers/specs/2026-06-27-candidate-route-p0-design.md docs/superpowers/specs/2026-06-27-candidate-route-p0-design.en.md
```

补充验证说明：

- `python -B -m unittest discover -s validation/tools -p "test_*.py"` 已尝试，但失败在既有 `validation/evidence/**` 生成证据 fixture：6 个 semantic gate 测试的 evidence manifest 缺少 schema 要求的 `c2rust_baseline` ref。失败发生在 JSON schema 校验阶段，早于本轮 external direct-callee validator 新逻辑；本轮仍不触碰这些预存脏 evidence 文件。

当前边界：

- 可以说：external direct-callee 的 source/signature/call-site binding 现在进入默认 validator 和 semantic-pass validator 的强一致性校验。
- 可以说：unsupported/blocked external direct-callee 会按 fail-closed evidence 校验，不要求 compile_only binding。
- 不应说：external callee 语义已经验证通过。stub 仍是 `compile_only`，`semantics_verified=false`，semantic acceptance 仍由 C oracle、Rust replay、schema diff、negative diff、unsafe ledger 和 final verification 决定。
- 不应说：完整 direct-call 系统已完成。函数指针、嵌套 call、condition call、副作用参数、未声明 external callee 的 blocked contract 更强校验仍可继续补。
- 仍不要 stage/revert/格式化 `validation/evidence/**` 中的预存脏文件。

English mirror summary:

- External direct-callee source/signature/call-site binding is now checked by the default validator path as well as the semantic-pass validator path.
- The validator now fails closed on missing call-site bindings, source hash drift, signature-shape drift, `callee_signature_id` drift, call-edge metadata drift, and stub/semantics-boundary drift.
- Unsupported blocked external callees are validated as fail-closed blocked evidence instead of being forced through compile-only binding.
- This is evidence-integrity and provenance hardening only. Recorded external callees remain `compile_only`, blocked external callees remain `stub_kind=none`, and `semantics_verified=false`; semantic acceptance still belongs to the validation gates.

## 87. 2026-06-27 scalar subtraction through typed IR and clang lowering

本轮继续按多智能体并行推进。只读线程结论一致：标量二元减法 `-` 是当前最小、高收益的 generic typed IR 扩展；FlashDB crc32 不应再新增或恢复任何专用 canned route，后续语义接受要走完整 validation gates。

核心改动：

- `crates/c2r-translator/src/typed_ir.rs`
  - `emit_binary_op()` 新增 `IrBinOp::Sub -> "-"`。
  - `validate_binary_operand_types()` 把 `-` 纳入与 `+` 相同的标量整数类型规则：lhs、rhs、result 必须发射为同一 Rust 标量类型。
- `crates/c2r-translator/src/clang_frontend.rs`
  - `ClangBinaryOperator` 新增 `Sub`。
  - clang AST `BinaryOperator opcode "-"` 现在 lowering 到 `ClangBinaryOperator::Sub`，再 lowering 到 `IrBinOp::Sub`。
  - `preserves_integral_operand_casts()` 纳入 `Sub`，避免 `unsigned int value - 1` 这类 usual arithmetic conversion 被剥掉后在 typed IR emitter 类型校验阶段误拒。
  - 新增内部单测覆盖 subtraction operand 的 `IntegralCast` 保留。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 direct typed IR 红绿测试 `typed_ir_emits_scalar_subtraction`。
  - 新增 clang skeleton 红绿测试 `typed_ir_emits_scalar_subtraction_from_clang_lowered_ir`，并断言 lhs/rhs 方向：`value - 1`，不能错成 `1 - value`。
  - 新增 gated real clang smoke `clang_ast_dump_emits_real_scalar_subtraction_when_enabled`，验证真实 C `int sub_one(int value) { return value - 1; }` 从 clang AST 到 typed IR，再到可编译 Rust。
- 文档同步：
  - `docs/c2rust-migration-agent/core-translation-architecture.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.en.md`
  - `docs/superpowers/specs/2026-06-27-candidate-route-p0-design.md`
  - `docs/superpowers/specs/2026-06-27-candidate-route-p0-design.en.md`
  - `docs/superpowers/plans/2026-06-27-candidate-route-p0.md`
  - `CONTEXT.md`

文档边界修订：

- 旧 `docs/superpowers/plans/2026-06-27-candidate-route-p0.md` 已改为 superseded tombstone，不再是可执行计划；它明确禁止恢复 `DeprecatedLegacyCrc32`、typed IR crc32 matcher、string translator crc32 byte-cursor recognizer 或 `crc32_update_byte()` canned template。
- `CONTEXT.md` 第 75、76、77 节已加历史状态警告，避免后续 agent 搜索到旧“当前”措辞后恢复 legacy crc32 fallback。
- candidate route P0 设计里的 “legacy route/profile evidence” 已改成“未带 candidate_generation 的历史 evidence artifacts”，避免把 legacy route 误读成当前允许路线。

已确认红灯：

```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_emits_scalar_subtraction -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend typed_ir_emits_scalar_subtraction_from_clang_lowered_ir -- --nocapture
```

红灯表现：

- direct typed IR 失败于 `binary op Sub is unsupported`。
- clang skeleton 失败于 `no variant or associated item named Sub found for enum ClangBinaryOperator`。

已跑过的聚焦验证：

```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_emits_scalar_subtraction -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend typed_ir_emits_scalar_subtraction_from_clang_lowered_ir -- --nocapture
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend clang_ast_dump_emits_real_scalar_subtraction_when_enabled -- --nocapture
```

当前边界：

- 可以说：direct typed IR、clang skeleton 和真实 clang AST 中的标量整数减法 `value - 1` 已经能进入 `GenericTypedIr` 并生成可编译 Rust。
- 可以说：`Sub` 保留 clang integral casts，覆盖 unsigned subtraction 的核心类型风险。
- 不应说：已支持所有 C 减号。`-value` 是 unary minus，`p - q` / `p - n` 是指针减法/指针算术，`-=` 是复合赋值；这些仍不在本轮能力范围内。
- 不应说：FlashDB semantic acceptance 已完成。FlashDB 只是用例；真实 generated draft 接受仍需要 C oracle、Rust replay、schema diff、negative diff、unsafe ledger、final verification。
- 仍不要 stage/revert/格式化 `validation/evidence/**` 中的预存脏文件。

English mirror summary:

- Scalar integer subtraction now flows through direct typed IR, clang skeleton lowering, and real clang AST smoke tests into `GenericTypedIr` and compilable Rust.
- `ClangBinaryOperator::Sub`, AST opcode `"-"`, cast-preserving operand lowering, and `IrBinOp::Sub` emission are all wired.
- The old Candidate Route P0 plan is now a superseded tombstone and must not be used to restore any crc32 canned or fallback route.
- This does not mean all C minus forms are supported: unary minus, pointer subtraction/arithmetic, and compound `-=` remain outside the current subset.
- This is still candidate generation only. Real FlashDB generated-draft semantic acceptance remains gated by C oracle, Rust replay, schema diff, negative diff, unsafe ledger, and final verification.

## 88. 2026-06-27 legacy auto-translation evidence backfill

本轮继续按多智能体并行推进。只读线程分别检查了 validator 强制检查点、文档同步点、下一核心翻译切口和提交边界。结论：

- 既有 6 个 demo semantic gate failure 的根因不是新翻译逻辑，而是 legacy accepted auto-translation fixture 缺少当前 schema/validator 要求的落盘证据绑定。
- 需要补的不只是 `evidence_manifest` 三个字段，还包括 auto manifest、final verification、cache metadata、translation plan、schema-aware diff、negative diff 和 Windows 工作树哈希绑定。
- `candidate_generation` 对历史 route/profile payload 仍可选；但这不等于 semantic-pass fixture 可以缺 `c2rust_baseline`、`route_decision`、`validation_profile` refs。

核心改动：

- 对 8 个 legacy accepted auto-translation fixtures 持久化三件套：
  - `l3-<slice>-c2rust-baseline-manifest.json`
  - `l3-<slice>-route-decision.json`
  - `l3-<slice>-validation-profile.json`
- 覆盖目录：
  - `validation/evidence/demo/auto-translation/add-i32-pair-ptr-arith`
  - `validation/evidence/demo/auto-translation/copy-i32-ptr-arith`
  - `validation/evidence/demo/auto-translation/external-direct-callee`
  - `validation/evidence/demo/auto-translation/store-add-one`
  - `validation/evidence/demo/auto-translation/sum-i32-buffer`
  - `validation/evidence/demo/auto-translation/sum-i32-ptr-arith`
  - `validation/evidence/libuv/auto-translation/ip4-addr`
  - `validation/evidence/zlib-ng/auto-translation/adler32-step`
- 路由结果按当前 router 记录，而不是全部硬写 L0：
  - L2: `add-i32-pair-ptr-arith`、`copy-i32-ptr-arith`、`sum-i32-buffer`、`sum-i32-ptr-arith`
  - L1: `store-add-one`、`libuv/ip4-addr`
  - L0: `external-direct-callee`、`zlib-ng/adler32-step`
- 每个 fixture 同步更新：
  - auto manifest 顶层 baseline/route/profile refs 和 cache dependent artifacts
  - L3 evidence manifest refs
  - final verification refs、`validation_profile_status=passed`、`skipped_gates=[]`
  - cache metadata 的 canonical JSON identities
  - schema-aware diff 的 `diff_gate`、accepted diff refs、required inputs
  - negative diff 的 `negative_diff_gate`、accepted negative diff refs、required inputs、mutation evidence
- `libuv` 和 `zlib-ng` 的 fixture/oracle 文件在 Windows 工作树为 CRLF，validator 按工作树字节计算 sha；本轮只刷新 auto-translation wrapper 中的工作树 sha refs，不提交顶层 fixture/oracle 文件。

已跑过的聚焦验证：

```powershell
python -B validation/tools/validate_auto_translation_evidence.py --target-id demo --slice-id add-i32-pair-ptr-arith --slice-spec validation/slice-specs/demo-add-i32-pair-ptr-arith.json --require-semantic-pass
python -B validation/tools/validate_auto_translation_evidence.py --target-id demo --slice-id copy-i32-ptr-arith --slice-spec validation/slice-specs/demo-copy-i32-ptr-arith.json --require-semantic-pass
python -B validation/tools/validate_auto_translation_evidence.py --target-id demo --slice-id external-direct-callee --slice-spec validation/slice-specs/demo-external-direct-callee.json --require-semantic-pass
python -B validation/tools/validate_auto_translation_evidence.py --target-id demo --slice-id store-add-one --slice-spec validation/slice-specs/demo-store-add-one.json --require-semantic-pass
python -B validation/tools/validate_auto_translation_evidence.py --target-id demo --slice-id sum-i32-buffer --slice-spec validation/slice-specs/demo-sum-i32-buffer.json --require-semantic-pass
python -B validation/tools/validate_auto_translation_evidence.py --target-id demo --slice-id sum-i32-ptr-arith --slice-spec validation/slice-specs/demo-sum-i32-ptr-arith.json --require-semantic-pass
python -B validation/tools/validate_auto_translation_evidence.py --target-id libuv --slice-id ip4-addr --slice-spec validation/slice-specs/libuv-ip4-addr.json --require-semantic-pass
python -B validation/tools/validate_auto_translation_evidence.py --target-id zlib-ng --slice-id adler32-step --slice-spec validation/slice-specs/zlib-adler32-step.json --require-semantic-pass
```

结果：8/8 semantic validators passed。

完整验证：

```powershell
python -B -m unittest discover -s validation/tools -p "test_*.py"
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend
openspec validate --all --strict
git diff --check
```

结果：

- `validation/tools`: 200 tests passed。
- `c2r-translator`: 20 lib tests + 180 bounded translation tests passed。
- `openspec`: 37 items passed。
- `git diff --check`: exit 0；Windows 工作树打印 LF/CRLF replacement warnings，但没有 whitespace error。

文档同步：

- `validation/auto-translation-template/README.md`
- `validation/auto-translation-template/checklist.md`
- `validation/l3-template/README.md`
- `validation/l3-template/checklist.md`
- `validation/README.md`
- `validation/gates.md`
- `docs/c2rust-migration-agent/core-translation-architecture.md`
- `docs/c2rust-migration-agent/core-translation-architecture.en.md`
- `CONTEXT.md`

当前边界：

- 可以说：legacy accepted auto-translation fixtures 现在按当前 validator 持久化 baseline/route/profile refs、schema-aware diff metadata 和 negative-diff mutation evidence。
- 可以说：这修复的是验证证据地基，能让 semantic gate tests 直接消费落盘 evidence，而不是靠 helper-only backfill。
- 不应说：这是新的翻译能力。下一步核心翻译切口建议继续做 generic typed IR 的 `*`、`/`、`%` 标量表达式。
- 不应说：C2Rust baseline 证明正确。baseline 仍是 `candidate_context_only`。
- 仍不要 stage/revert/格式化顶层 `validation/evidence/**` 预存脏文件；提交时必须使用 auto-translation 目录和文档白名单。

English mirror summary:

- Legacy accepted auto-translation fixtures now persist baseline/route/profile refs, schema-aware diff metadata, and negative-diff mutation evidence required by the current semantic-pass validator.
- This is validation evidence hardening, not a new translator capability.
- The route levels are recorded by the current router instead of forcing every legacy fixture to L0.
- C2Rust baseline remains `candidate_context_only`; semantic acceptance still belongs to validation profile gates.
- The next core translation cut should keep extending generic typed IR scalar expressions, with `*`, `/`, and `%` as the next narrow target.

## 89. 2026-06-27 scalar multiplication/division/modulo through typed IR and clang lowering

本轮继续按多智能体并行推进。只读线程分别复核了代码切口、文档边界和提交白名单；主线程按 TDD 把标量整数 `*`、`/`、`%` 从 clang skeleton/真实 clang AST 接到 `GenericTypedIr` emitter。结论是：这是一条 generic typed IR candidate generation 能力，不是 FlashDB 专用代码，也不是 semantic acceptance。

核心改动：
- `crates/c2r-translator/src/typed_ir.rs`
  - `emit_binary_op()` 新增 `IrBinOp::Mul -> "*"`、`IrBinOp::Div -> "/"`、`IrBinOp::Mod -> "%"`.
  - `validate_binary_operand_types()` 把 `*`、`/`、`%` 纳入与 `+`、`-`、`&`、`^` 相同的窄标量规则：lhs、rhs、result 必须发射为同一个 Rust 标量类型。
- `crates/c2r-translator/src/clang_frontend.rs`
  - `ClangBinaryOperator` 新增 `Mul`、`Div`、`Mod`.
  - clang AST `BinaryOperator` opcode `"*"`, `"/"`, `"%"` 现在 lowering 到对应 skeleton operator，再 lowering 到 `IrBinOp`.
  - `preserves_integral_operand_casts()` 纳入 `Mul`、`Div`、`Mod`，避免 unsigned/integral cast operand 被过早剥掉后导致 typed IR 类型校验误拒。
  - 新增内部单测覆盖 multiplicative operands 的 `IntegralCast` 保留与 lowering。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 direct typed IR 正向测试 `typed_ir_emits_scalar_mul_div_mod`.
  - 新增 clang skeleton 正向测试 `typed_ir_emits_scalar_mul_div_mod_from_clang_lowered_ir`.
  - 新增负例 `typed_ir_rejects_mismatched_mul_div_mod_operand_types_in_generic_emitter`，分别覆盖 `Mul`、`Div`、`Mod` 类型不一致必须 fail closed。
  - 新增 gated real clang smoke `clang_ast_dump_emits_real_scalar_mul_div_mod_when_enabled`，覆盖真实 C `int mul_div_mod(int value) { return ((value * 3) / 2) % 5; }` 从 clang AST 到 typed IR 再到可编译 Rust candidate。
- 双语文档已同步：
  - `docs/c2rust-migration-agent/README.md`
  - `docs/c2rust-migration-agent/README.en.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.en.md`
  - `docs/superpowers/specs/2026-06-27-candidate-route-p0-design.md`
  - `docs/superpowers/specs/2026-06-27-candidate-route-p0-design.en.md`

已确认红灯：

```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_emits_scalar_mul_div_mod -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend typed_ir_emits_scalar_mul_div_mod_from_clang_lowered_ir -- --nocapture
```

红灯表现：
- direct typed IR 失败于 `stmt[0].return expr binary op Mod is unsupported`.
- clang skeleton 失败于 `no variant or associated item named Mul/Div/Mod found for enum ClangBinaryOperator`.

已跑过的聚焦验证：

```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_emits_scalar_mul_div_mod -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_rejects_mismatched_mul_div_mod_operand_types_in_generic_emitter -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend typed_ir_emits_scalar_mul_div_mod_from_clang_lowered_ir -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend expr_skeleton_from_ast_preserves_multiplicative_integral_cast_operands -- --nocapture
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend clang_ast_dump_emits_real_scalar_mul_div_mod_when_enabled -- --nocapture
```

提交前需要保留的完整验证：

```powershell
cargo fmt --manifest-path crates/c2r-translator/Cargo.toml -- --check
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend
cargo clippy --manifest-path crates/c2r-translator/Cargo.toml --all-targets --features typed-ir,clang-frontend -- -D warnings
openspec validate --all --strict
git diff --ignore-cr-at-eol --check
```

最终验证结果：
- `cargo fmt --manifest-path crates/c2r-translator/Cargo.toml -- --check`: PASS。
- `$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend`: PASS，21 lib tests + 184 bounded translation tests passed，真实 clang AST `mul_div_mod` smoke 实际运行通过。
- `cargo clippy --manifest-path crates/c2r-translator/Cargo.toml --all-targets --features typed-ir,clang-frontend -- -D warnings`: PASS。
- `openspec validate --all --strict`: PASS，37 items passed。
- `git diff --ignore-cr-at-eol --check`: PASS；Windows 工作树仍打印 LF/CRLF replacement warnings，但没有 whitespace error。

当前边界：
- 可以说：direct typed IR、clang skeleton 和真实 clang AST smoke 覆盖的标量整数乘法、除法、取模表达式，现在能进入 `GenericTypedIr` 并生成可编译 Rust candidate。
- 可以说：`Mul`、`Div`、`Mod` 保留 clang integral casts，避免 covered unsigned/integral operand 被错误剥离。
- 不应说：已经支持除零、完整 C 算术、浮点算术、完整 usual arithmetic conversions、overflow/UB parity、指针算术、pointer difference、array-to-pointer decay、复合赋值或 inc/dec。
- 除法/取模只有在 divisor 非零由 literal、fixture 输入域或 slice contract 明确约束时，才能继续进入后续 semantic gate；否则不得提升 semantic acceptance，必要时 fail closed。
- FlashDB 仍只是用例；这轮没有恢复任何 crc32 专用 route、typed IR crc32 matcher 或 canned template。
- 仍不要 stage/revert/格式化顶层 `validation/evidence/**` 预存脏文件；提交必须用白名单。

English mirror summary:

- Scalar integer multiplication, division, and modulo now flow through direct typed IR, clang skeleton lowering, and real clang AST smoke tests into `GenericTypedIr` and compilable Rust candidates.
- `ClangBinaryOperator::{Mul, Div, Mod}`, AST opcodes `"*"`, `"/"`, `"%"`, cast-preserving operand lowering, and `IrBinOp::{Mul, Div, Mod}` emission are wired.
- This is candidate generation only. It does not support division by zero, all C arithmetic, floating-point arithmetic, full usual arithmetic conversions, overflow/UB parity, pointer arithmetic, pointer difference, array-to-pointer decay, compound assignment, or inc/dec.
- Division and modulo may only move toward semantic acceptance when a non-zero divisor is established by a literal, fixture input domain, or slice contract; otherwise the path must stay fail-closed.
- FlashDB remains only a use case. This slice does not restore any crc32-specific route, typed IR crc32 matcher, or canned template.

## 90. 2026-06-27 signed unary minus through typed IR and clang lowering

本轮继续按多智能体并行推进核心翻译切口。只读线程分别复核了测试组合、文档同步点和验证矩阵；主线按 TDD 把 signed unary minus `-value` 从 clang AST/skeleton lowering 接到 `GenericTypedIr` emitter。结论：这是 generic typed IR candidate generation 能力，不是 FlashDB 专用代码，也不是 semantic acceptance。

核心改动：
- `crates/c2r-translator/src/typed_ir.rs`
  - `IrUnOp::Neg` 现在由 generic typed IR emitter 发射为 `(-operand)`。
  - 新增 signed-only 校验：operand/result 必须是同一个 signed integer scalar type；unsigned result、unsigned operand、非 scalar 或 signed width mismatch 必须 fail closed。
- `crates/c2r-translator/src/clang_frontend.rs`
  - `ClangUnaryOperator` 新增 `Neg`。
  - clang AST `UnaryOperator` opcode `"-"` 现在 lowering 到 `ClangUnaryOperator::Neg`，再 lowering 到 `IrUnOp::Neg`。
  - 新增默认单测覆盖 `UnaryOperator("-") -> IrUnOp::Neg`，不依赖真实 clang 环境。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 direct typed IR 正向测试 `typed_ir_emits_signed_unary_minus`。
  - 新增 clang skeleton 正向测试 `typed_ir_emits_signed_unary_minus_from_clang_lowered_ir`。
  - 新增负例 `typed_ir_rejects_unsigned_unary_minus_in_generic_emitter` 和 `typed_ir_rejects_mismatched_signed_unary_minus_type_in_generic_emitter`。
  - 新增 `typed_ir_rejects_logical_not_in_generic_emitter`，明确 `IrUnOp::Not` 仍不被 generic emitter 支持，避免误发射成 Rust `!`。
  - 新增 gated real clang smoke `clang_ast_dump_emits_real_signed_unary_minus_when_enabled`，覆盖真实 C `int neg_value(int value) { return -value; }`。
- `crates/c2r-translator/src/lib.rs`
  - 为通过当前 clippy gate，等价合并了 `emit_ir_pointer_graph()` 中 `rust_boundary` 的重复 `&[u8]` 分支：`param.name == "buf" || is_const_input`。这不改变 pointer graph 语义。
- 双语文档已同步：
  - `docs/c2rust-migration-agent/README.md`
  - `docs/c2rust-migration-agent/README.en.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.en.md`
  - `docs/superpowers/specs/2026-06-27-candidate-route-p0-design.md`
  - `docs/superpowers/specs/2026-06-27-candidate-route-p0-design.en.md`

已确认红灯：
```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_emits_signed_unary_minus -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend typed_ir_emits_signed_unary_minus_from_clang_lowered_ir -- --nocapture
```

红灯表现：
- direct typed IR 失败于 `stmt[0].return expr unary op Neg is unsupported`。
- clang skeleton 失败于 `no variant or associated item named Neg found for enum ClangUnaryOperator`。

已跑过的聚焦验证：
```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_emits_signed_unary_minus -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_rejects_unsigned_unary_minus_in_generic_emitter -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_rejects_logical_not_in_generic_emitter -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend typed_ir_emits_signed_unary_minus_from_clang_lowered_ir -- --nocapture
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend clang_ast_dump_emits_real_signed_unary_minus_when_enabled -- --nocapture
```

提交前最终验证结果：
- `cargo fmt --manifest-path .\crates\c2r-translator\Cargo.toml -- --check`: PASS。
- `cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-lowering-report`: PASS，26 lib tests + 191 bounded translation tests passed。
- `$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-lowering-report --test bounded_translation clang_ast_dump_emits_real_signed_unary_minus_when_enabled -- --nocapture`: PASS，1 test passed，真实 clang AST smoke 实际运行。
- `cargo clippy --manifest-path .\crates\c2r-translator\Cargo.toml --all-targets --features clang-lowering-report -- -D warnings`: PASS。
- `openspec validate --all --strict`: PASS，37 items passed。
- `git diff --check -- <本轮意图提交文件白名单>`: PASS；Windows 工作树仍打印 LF/CRLF replacement warnings，但没有 whitespace error。

当前边界：
- 可以说：direct typed IR、clang skeleton 和真实 clang AST smoke 覆盖的 signed scalar unary minus 现在能进入 `GenericTypedIr` 并生成可编译 Rust candidate。
- 可以说：typed IR emitter 会拒绝 unsigned unary minus 和 signed operand/result width mismatch。
- 可以说：`IrUnOp::Not` 仍有 fail-closed 回归覆盖，本轮没有把 logical not 接成 Rust `!`。
- 不应说：已经支持完整 C unary minus。unsigned/wrapping 取负、浮点取负、指针算术、复合 `-=`, literal/min-value 边界如 `-2147483648`、以及完整 usual arithmetic conversions 仍未建模，必须继续 fail closed。
- FlashDB 仍只是用例；本轮没有恢复任何 crc32 专用 route、typed IR crc32 matcher 或 canned template。
- 仍不要 stage/revert/格式化顶层 `validation/evidence/**` 预存脏文件；提交必须使用白名单。

English mirror summary:

- Signed scalar unary minus now flows through direct typed IR, clang skeleton lowering, and a real clang AST smoke test into `GenericTypedIr` and compilable Rust candidates.
- `ClangUnaryOperator::Neg`, AST opcode `"-"`, and `IrUnOp::Neg` emission are wired.
- The emitter is signed-only and requires operand/result to be the same signed integer scalar type; unsigned unary minus and signed width mismatch fail closed.
- `IrUnOp::Not` remains fail-closed and is covered by a regression test; this slice does not emit Rust `!`.
- This is candidate generation only. It does not support unsigned/wrapping negation, floating-point negation, pointer arithmetic, compound `-=`, literal/min-value edge cases such as `-2147483648`, full usual arithmetic conversions, or semantic acceptance.
- FlashDB remains only a use case. This slice does not restore any crc32-specific route, typed IR crc32 matcher, or canned template.

## 91. 2026-06-27 condition-only logical not through typed IR and clang lowering

本轮继续按多智能体并行推进核心翻译切口。只读线程分别复核了 typed IR condition emitter、clang AST `UnaryOperator` lowering 和中英文文档同步点；主线程按 TDD 把仅条件位置的 C logical not `!expr` 接入 `GenericTypedIr` candidate generation。结论：这是通用 typed IR candidate generation 能力，不是 FlashDB 专用代码，也不是 semantic acceptance。

核心改动：
- `crates/c2r-translator/src/typed_ir.rs`
  - `emit_condition_expr()` 现在在 `if` / `while` 条件位置识别 `IrUnOp::Not`。
  - `if (!value)` / `while (!value)` 生成整数零比较，例如 `value == 0i32`，避免误用 Rust 整数位取反 `!value`。
  - `!(value > 0)` 生成反转后的 comparison condition，例如 `value <= 0i32`，不把 comparison 当作 value expression 或 integer truthiness 包装。
  - logical-not 表达式结果类型必须是 C `int`；operand 含 call、inc/dec、未建模 side effect、pointer/float/unsupported type 继续 fail closed。
  - `emit_expr()` 没有放开 `IrUnOp::Not`，所以 value-position `return !value` 仍 fail closed。
- `crates/c2r-translator/src/clang_frontend.rs`
  - `ClangUnaryOperator` 新增 `Not`。
  - clang AST `UnaryOperator` opcode `"!"` 现在 lowering 到 `ClangUnaryOperator::Not`，再 lowering 到 `IrUnOp::Not`。
  - 新增内部 JSON 单测覆盖 `UnaryOperator("!") -> IrUnOp::Not`，不依赖真实 clang 环境。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 direct typed IR 正向测试 `typed_ir_emits_scalar_if_with_logical_not_integer_condition`。
  - 新增 direct typed IR 正向测试 `typed_ir_emits_scalar_while_with_logical_not_integer_condition`。
  - 新增 direct typed IR 正向测试 `typed_ir_emits_scalar_if_with_logical_not_comparison_condition`。
  - 新增 fail-closed 测试 `typed_ir_rejects_logical_not_condition_with_incdec_operand` 和 `typed_ir_rejects_logical_not_condition_with_non_int_result_type`。
  - 既有 `typed_ir_rejects_logical_not_in_generic_emitter` 保持 value-position `IrUnOp::Not` fail-closed。
  - 新增 clang skeleton 测试 `clang_lowering_skeleton_maps_logical_not_if_condition`。
  - 新增 gated real clang smoke `clang_ast_dump_emits_logical_not_if_condition_when_enabled`，覆盖真实 C `int is_zero(int value) { if (!value) { return 1; } return 0; }`。
- 双语文档已同步：
  - `docs/c2rust-migration-agent/README.md`
  - `docs/c2rust-migration-agent/README.en.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.en.md`
  - `docs/superpowers/specs/2026-06-27-candidate-route-p0-design.md`
  - `docs/superpowers/specs/2026-06-27-candidate-route-p0-design.en.md`

已确认红灯：
```powershell
cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features typed-ir typed_ir_emits_scalar_if_with_logical_not_integer_condition -- --nocapture
cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-lowering-report clang_lowering_skeleton_maps_logical_not_if_condition -- --nocapture
```

红灯表现：
- direct typed IR 失败于 `stmt[0].if condition unary op Not is unsupported`。
- clang skeleton 失败于 `no variant or associated item named Not found for enum ClangUnaryOperator`。

已跑过的聚焦验证：
```powershell
cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-lowering-report logical_not -- --nocapture
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-lowering-report --test bounded_translation clang_ast_dump_emits_logical_not_if_condition_when_enabled -- --nocapture
```

提交前最终验证结果：
- `cargo fmt --manifest-path .\crates\c2r-translator\Cargo.toml -- --check`: PASS。
- `cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-lowering-report`: PASS，27 lib tests + 198 bounded translation tests passed。
- `$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-lowering-report --test bounded_translation clang_ast_dump_emits_logical_not_if_condition_when_enabled -- --nocapture`: PASS，真实 clang AST smoke 实际运行。
- `cargo clippy --manifest-path .\crates\c2r-translator\Cargo.toml --all-targets --features clang-lowering-report -- -D warnings`: PASS。
- `openspec validate --all --strict`: PASS，37 items passed。
- `git diff --check -- <本轮意图提交文件白名单>`: PASS；Windows 工作树仍打印 LF/CRLF replacement warnings，但没有 whitespace error。

当前边界：
- 可以说：direct typed IR、clang skeleton 和真实 clang AST smoke 覆盖的 condition-only logical not 现在能进入 `GenericTypedIr` 并生成可编译 Rust candidate。
- 可以说：`if (!value)` / `while (!value)` 使用整数零比较；`!(value > 0)` 使用反转 comparison condition。
- 可以说：value-position `IrUnOp::Not` 仍有 fail-closed 回归覆盖；本轮没有把 `return !value`、assignment RHS 或 declaration initializer 的 C `int` 结果语义接入 generic emitter。
- 不应说：已经支持完整 C unary `!`、短路逻辑、pointer null test、float truthiness、call/deref/inc/dec side-effect operand、或者 semantic acceptance。
- FlashDB 仍只是用例；本轮没有恢复任何 crc32 专用 route、typed IR crc32 matcher 或 canned template。
- 仍不要 stage/revert/格式化顶层 `validation/evidence/**` 预存脏文件；提交必须使用白名单。

English mirror summary:

- Condition-only logical not now flows through direct typed IR, clang skeleton lowering, and a real clang AST smoke test into `GenericTypedIr` and compilable Rust candidates.
- `ClangUnaryOperator::Not`, AST opcode `"!"`, and `IrUnOp::Not` condition emission are wired.
- `if (!value)` / `while (!value)` emit integer zero comparisons; `!(value > 0)` emits a negated comparison condition.
- Value-position `IrUnOp::Not` remains fail-closed, so C `int` result semantics such as `return !value`, assignment RHS, and declaration initializer are not supported yet.
- This is candidate generation only. It does not support full C unary `!`, short-circuit logic, pointer null tests, floating-point truthiness, call/deref/inc/dec side-effect operands, or semantic acceptance.
- FlashDB remains only a use case. This slice does not restore any crc32-specific route, typed IR crc32 matcher, or canned template.

## 92. 2026-06-27 value-position logical not through typed IR and clang lowering

本轮继续按多智能体并行推进核心翻译切口。只读线程分别复核了 typed IR value-position 发射点、clang AST `UnaryOperator("!")` 已有 lowering、边界测试缺口、文档同步点和最终 diff；主线程按 TDD 把 C logical not `!expr` 的窄 value-position C `int` 0/1 结果语义接入 `GenericTypedIr` candidate generation。结论：这是通用 typed IR scalar expression 能力，不是 FlashDB 专用代码，也不是 semantic acceptance。

核心改动：
- `crates/c2r-translator/src/typed_ir.rs`
  - `emit_expr()` 现在支持 `IrUnOp::Not` 的 value-position。
  - 新增 value materialization helper：先复用 logical-not condition lowering，再生成 `(if condition { 1i32 } else { 0i32 })`；它不是 Rust `!value`。
  - logical-not result type 继续要求 C `int`，也就是 signed 32-bit integer；operand 的零值按 operand type 生成，例如 `unsigned char value` 发 `value == 0u8`，外层结果仍发 `1i32` / `0i32`。
  - comparison operand 继续走反转 comparison，例如 `!(value > 0)` value-position 发 `(if (value <= 0i32) { 1i32 } else { 0i32 })`，不发 `(value > 0) == 0`。
  - operand 内含 call 时递归 fail closed；inc/dec、deref、pointer、unsupported type 等继续由 typed IR emitter fail closed。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 direct typed IR 正向测试 `typed_ir_emits_logical_not_return_value`。
  - 新增 direct typed IR 正向测试 `typed_ir_emits_logical_not_u8_operand_as_c_int_value`。
  - 新增 direct typed IR 正向测试 `typed_ir_emits_logical_not_assignment_value`。
  - 新增 direct typed IR 正向测试 `typed_ir_emits_logical_not_decl_initializer`。
  - 新增 direct typed IR 正向测试 `typed_ir_emits_logical_not_comparison_return_value`。
  - 新增 direct typed IR 正向测试 `typed_ir_emits_logical_not_as_comparison_condition_operand`，覆盖 `!value` 作为 condition comparison operand 的上下文。
  - 新增 fail-closed 测试 `typed_ir_rejects_value_comparison_with_logical_not_operand`，明确 `return (!value) == 1` 这类 value-position comparison 仍属于下一切口。
  - 新增 fail-closed 测试 `typed_ir_rejects_logical_not_value_with_call_operand`、`typed_ir_rejects_logical_not_value_with_incdec_operand`、`typed_ir_rejects_logical_not_value_with_deref_operand`、`typed_ir_rejects_logical_not_value_with_pointer_operand`、`typed_ir_rejects_logical_not_value_with_unsupported_operand_type` 和 `typed_ir_rejects_logical_not_value_with_non_int_result_type`。
  - 新增 clang skeleton 测试 `clang_lowering_skeleton_maps_logical_not_return_value`。
  - 新增 gated real clang smoke `clang_ast_dump_emits_logical_not_return_value_when_enabled`、`clang_ast_dump_emits_logical_not_decl_initializer_when_enabled` 和 `clang_ast_dump_emits_logical_not_assignment_value_when_enabled`。
- 双语文档已同步：
  - `docs/c2rust-migration-agent/README.md`
  - `docs/c2rust-migration-agent/README.en.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.en.md`
  - `docs/superpowers/specs/2026-06-27-candidate-route-p0-design.md`
  - `docs/superpowers/specs/2026-06-27-candidate-route-p0-design.en.md`

已确认红灯：
```powershell
cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features typed-ir typed_ir_emits_logical_not_return_value -- --nocapture
cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-lowering-report clang_lowering_skeleton_maps_logical_not_return_value -- --nocapture
```

红灯表现：
- direct typed IR 失败于 `stmt[0].return expr unary op Not is unsupported`。
- clang skeleton 已能 lowering 到 `IrUnOp::Not`，但 Rust 发射仍失败于 `stmt[0].return expr unary op Not is unsupported`。

已跑过的聚焦验证：
```powershell
cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-lowering-report logical_not -- --nocapture
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-lowering-report --test bounded_translation clang_ast_dump_emits_logical_not -- --nocapture
```

提交前最终验证结果：
- `cargo fmt --manifest-path .\crates\c2r-translator\Cargo.toml -- --check`: PASS。
- `cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-lowering-report`: PASS，27 lib tests + 214 bounded translation tests passed。
- `$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-lowering-report --test bounded_translation clang_ast_dump_emits_logical_not -- --nocapture`: PASS，4 real clang AST smoke tests actually ran。
- `cargo clippy --manifest-path .\crates\c2r-translator\Cargo.toml --all-targets --features clang-lowering-report -- -D warnings`: PASS。
- `openspec validate --all --strict`: PASS，37 items passed。
- `git diff --check -- <本轮意图提交文件白名单>`: PASS；Windows 工作树仍打印 LF/CRLF replacement warnings，但没有 whitespace error。

当前边界：
- 可以说：direct typed IR、clang skeleton 和真实 clang AST smoke 覆盖的 value-position logical not 现在能进入 `GenericTypedIr` 并生成可编译 Rust candidate。
- 可以说：`return !value`、assignment RHS、declaration initializer 和 `!(value > 0)` value materialization 会生成 C `int` 0/1 结果，而不是 Rust integer bitwise `!`。
- 可以说：operand 零值按 operand type 生成，result 固定为 C `int`，所以 `unsigned char value` 会发 `value == 0u8` 和 `1i32` / `0i32`。
- 不应说：已经支持完整 C unary `!`、短路逻辑、pointer null test、float truthiness、call/deref/inc/dec side-effect operand、完整 usual scalar conversions、或 semantic acceptance。
- FlashDB 仍只是用例；本轮没有恢复任何 crc32 专用 route、typed IR crc32 matcher 或 canned template。
- 仍不要 stage/revert/格式化顶层 `validation/evidence/**` 预存脏文件；提交必须使用白名单。

下一步建议：
- 下一小步核心翻译切口建议是 value-position comparison expression 的 C `int` 0/1 结果语义，例如 `return x > 0`、`out = x == y`、`int ok = x != 0`。
- 该切口和本轮 logical not 共用 `bool condition -> C int materialization` 问题，但仍要保持 pointer comparison、float comparison、mixed-width/unsigned conversion、side-effect operands、short-circuit `&&` / `||` 和 semantic acceptance fail closed。

English mirror summary:

- Narrow value-position logical not now flows through direct typed IR, clang skeleton lowering, and real clang AST smoke tests into `GenericTypedIr` and compilable Rust candidates.
- `emit_expr()` supports `IrUnOp::Not` by materializing C `int` 0/1 as `(if condition { 1i32 } else { 0i32 })`, not Rust `!value`.
- `return !value`, assignment RHS, declaration initializer, and value-position `!(value > 0)` are covered.
- Operand zero literals use the operand type, while the outer result remains C `int`; for example an `unsigned char` operand emits `value == 0u8` with `1i32` / `0i32` results.
- This is candidate generation only and keeps `semantic_pass=false`. It does not support full C unary `!`, short-circuit logic, pointer null tests, floating-point truthiness, call/deref/inc/dec side-effect operands, full usual scalar conversions, or semantic acceptance.
- FlashDB remains only a use case. This slice does not restore any crc32-specific route, typed IR crc32 matcher, or canned template.

## 93. 2026-06-27 value-position comparison through typed IR and clang lowering

本轮继续按多智能体并行推进核心翻译切口。只读线程分别复核了 typed IR comparison emitter、clang lowering 现状、文档同步点和验证风险；主线程按 TDD 把窄 value-position comparison expression 的 C `int` 0/1 结果语义接入 `GenericTypedIr` candidate generation。结论：这是通用 typed IR scalar expression 能力，不是 FlashDB 专用代码，也不是 semantic acceptance。

核心改动：
- `crates/c2r-translator/src/typed_ir.rs`
  - `emit_expr()` 和 `emit_expr_with_prelude()` 现在识别 comparison `IrExpr::Binary` 的 value-position。
  - 新增 `emit_comparison_condition_from_parts()`，让 condition-position 和 value-position comparison 共用同一套 scalar comparison 校验与 Rust bool condition 生成。
  - 新增 `emit_comparison_value_expr()`，把 `return x > 0`、assignment RHS、declaration initializer 里的 comparison materialize 为 `(if condition { 1i32 } else { 0i32 })`，保持 C `int` 0/1 语义。
  - `if` / `while` 条件里的 comparison 仍发射 Rust bool condition，不额外 materialize 成整数。
  - comparison result type 必须是 C `int`；pointer comparison、float/unsupported comparison、mixed-width/unsigned conversions、call/inc/dec/deref side-effect operands、short-circuit `&&` / `||` 继续 fail closed。历史说明：本节写作时 comparison cast operand 仍 fail closed；第 97 节已窄化放开 source/target 都是可发射整数类型且 cast 后两侧类型完全一致的 integral cast operand。
- `crates/c2r-translator/src/clang_frontend.rs`
  - comparison lowering 本身没有 production 改动；既有 clang AST lowering 已经能把真实 TU 中的 `>`, `==`, `!=` comparison lowering 成 result type 为 `int` 的 typed IR binary expression。
  - 额外修复 `clang-frontend` feature 单独编译时的 dry-run 路径：`normalized_path(path: &Path)` 需要无条件导入 `std::path::Path`，否则 `--emit-clang-dry-run` 会在该 feature 组合下编译失败。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 direct typed IR 正向测试：return value、assignment RHS、declaration initializer、`u8` operand comparison result、logical-not operand 嵌套 materialization。
  - 新增 fail-closed 测试：call operand、inc/dec operand、deref operand、pointer operand、float/unsupported operand、mismatched operand types、mismatched operand widths、non-C-int result type、short-circuit logical ops、`*p++ == 0` 这类需要 prelude 的 byte-read operand，以及 condition-position 的 pointer/unsupported/deref/short-circuit 边界。历史说明：comparison cast operand 的窄化整数 cast 情况已由第 97 节改成正向发射测试。
  - 新增 clang skeleton 测试：comparison return value、declaration initializer、assignment RHS。
  - 新增 gated real clang smoke：真实 C `return x > 0`、decl initializer、assignment value 的 comparison AST lowering。
- 双语文档已同步：
  - `docs/c2rust-migration-agent/README.md`
  - `docs/c2rust-migration-agent/README.en.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.en.md`
  - `docs/superpowers/specs/2026-06-27-candidate-route-p0-design.md`
  - `docs/superpowers/specs/2026-06-27-candidate-route-p0-design.en.md`

已确认红灯：
```powershell
cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-lowering-report comparison -- --nocapture
```

红灯表现：
- value-position comparison 正向用例失败于 `binary op ... is unsupported`。
- 新增 fail-closed 用例在实现前只能得到旧的 generic unsupported 错误，无法给出具体边界原因。

已跑过的聚焦绿灯：
```powershell
cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-lowering-report comparison -- --nocapture
```

聚焦结果：PASS，`comparison` filter 下 1 个 lib test + 40 个 bounded translation tests 通过。

提交前最终验证结果：
- `cargo fmt --manifest-path .\crates\c2r-translator\Cargo.toml -- --check`: PASS。
- `cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-lowering-report`: PASS，27 个 lib tests + 238 个 bounded translation tests + doc-tests 通过。
- `$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-lowering-report --test bounded_translation clang_ast_dump_emits_comparison -- --nocapture`: PASS，4 个真实 clang comparison AST smoke tests 实际运行并通过。
- `cargo clippy --manifest-path .\crates\c2r-translator\Cargo.toml --all-targets --features clang-lowering-report -- -D warnings`: PASS。
- `cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend clang_dry_run -- --nocapture`: PASS，2 个 clang dry-run tests 通过。
- `python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_real_fdb_calc_crc32_emit_clang_dry_run_opt_in_writes_temp_artifact -v`: PASS。
- `cargo clippy --manifest-path .\crates\c2r-translator\Cargo.toml --all-targets --features clang-frontend -- -D warnings`: PASS。
- `openspec validate --all --strict`: PASS，37 items passed。
- `git diff --check -- <本轮意图提交文件白名单>`: PASS；Windows 工作树仍打印 LF/CRLF replacement warnings，但没有 whitespace error。
- `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-full-regression.ps1 -Rounds 1`: extra full-regression smoke run `20260627T001827Z` reached step 31/35 and failed on pre-existing `validation/evidence/flashdb/l3-kvdb-compact-overwrite-summary.json` hash drift: declared c_oracle sha256 `2b7f57daca9a5bd905235c52f9fad96bd6e7abf67fda1bf4b94eaf261717e5ea`, actual `6003d05f935938f737445396fa5ae104cfccd08fd14a1a692dfb3a82f5e792f3`. This is outside the current commit whitelist and `validation/evidence/**` remains unstaged.

当前边界：
- 可以说：direct typed IR、clang skeleton 和真实 clang AST smoke 覆盖的窄 value-position comparison expression 现在能进入 `GenericTypedIr` 并生成可编译 Rust candidate。
- 可以说：`return x > 0`、`out = x == y`、declaration initializer 和 `u8` scalar operand 的 comparison result 会生成 C `int` 0/1，而不是 Rust bool value。
- 可以说：`if` / `while` 中的 comparison 仍生成 Rust bool condition。
- 不应说：已经支持完整 C comparison expression、pointer comparison、float comparison、未由显式整数 cast 对齐的 mixed-width/unsigned conversions、short-circuit `&&` / `||`、call/deref/inc/dec side-effect operands、usual arithmetic conversions 或 semantic acceptance。
- FlashDB 仍只是用例；本轮没有恢复任何 crc32 专用 route、typed IR crc32 matcher 或 canned template。
- 本轮额外修了 `clang-frontend` dry-run feature 编译缺口；它只保证 `--emit-clang-dry-run` feature 组合能编译并写出 dry-run artifact，不改变 comparison lowering 语义。
- 本节已经 supersede 第 92 节末尾“下一小步建议 value-position comparison”的历史建议；后续继续按最新编号章节读取。

下一步建议：
- 下一小步核心翻译切口建议继续沿 scalar expression 覆盖面推进，但不要把 short-circuit、usual arithmetic conversions 或 pointer/null comparison 混进同一刀；这些需要单独设计 fail-closed 边界和 oracle。
- 如果要提高真实项目覆盖率，优先补 typed IR 的 casts/usual conversions 观测与 fail-closed 分类，再决定哪些转换可以安全 deterministic emit。

English mirror summary:

- Narrow value-position comparison expressions now flow through direct typed IR, clang skeleton lowering, and real clang AST smoke tests into `GenericTypedIr` and compilable Rust candidates.
- `emit_expr()` and `emit_expr_with_prelude()` support comparison `IrExpr::Binary` values by materializing C `int` 0/1 as `(if condition { 1i32 } else { 0i32 })`, not as Rust bool values.
- `if` / `while` comparison conditions still emit Rust bool conditions.
- This slice did not need comparison-lowering production changes in `clang_frontend.rs`; existing lowering already maps real `>`, `==`, and `!=` AST nodes to typed IR binary expressions with C `int` result type. It also fixes a separate `clang-frontend` dry-run feature compile gap by importing `std::path::Path` unconditionally.
- This is candidate generation only and keeps `semantic_pass=false`. It does not support full C comparison semantics, pointer comparison, floating-point comparison, mixed-width/unsigned conversions not aligned by explicit integer casts, short-circuit `&&` / `||`, call/deref/inc/dec side-effect operands, usual arithmetic conversions, or semantic acceptance.
- FlashDB remains only a use case. This slice does not restore any crc32-specific route, typed IR crc32 matcher, or canned template.

## 94. 2026-06-27 FlashDB L3 evidence hash drift and Windows fake compiler timeout fix

本轮只处理验证链稳定性问题，没有新增翻译能力，也没有改变 FlashDB L3 行为边界。前一轮 full-regression 在 step 31/35 暴露 `validation/evidence/flashdb/l3-kvdb-compact-overwrite-summary.json` 中已声明的 evidence `sha256` 与实际文件内容漂移；本轮将 4 个过期 hash 刷新到当前已提交的 evidence 文件内容，并修复 Windows fake compiler 在单测中复制 `cmd.exe` 后执行可能卡住 30s 的随机 timeout 问题。

核心改动：
- `validation/evidence/flashdb/l3-kvdb-compact-overwrite-summary.json`
  - 刷新 `c_oracle.sha256`。
  - 刷新 `c_oracle_producer_evidence.sha256`。
  - 刷新 `mutated_value_or_entries_oracle.sha256`。
  - 刷新 `summary_md.sha256`。
- `validation/tools/test_auto_migrate.py`
  - Windows fake compiler 不再把 `%COMSPEC%` / `cmd.exe` 复制为输出可执行文件。
  - 改为复制 `SystemRoot` / `WINDIR` 下的 `System32/hostname.exe`，作为稳定零退出可执行文件，避免 harness 执行阶段随机卡到 30s timeout。
  - fake `cc` 和 fake `gcc` helper 均同步修正。

已验证：
- `python -B validation/tools/validate_flashdb_l3_evidence.py --evidence-root validation/evidence --report target/tmp/flashdb-l3-evidence-after-kvdb-hash.json`: PASS，FlashDB L3 strict package `kvdb-compact-overwrite` 可被 validator 消费。
- 额外全量扫描 FlashDB passed summary 的 summary-declared evidence hash：`checked_refs 19`，`mismatch_count 0`。
- `python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_compile_success_records_harness_execution_without_oracle_claim validation.tools.test_auto_migrate.AutoMigrateTests.test_cc_compile_command_falls_back_to_gcc_when_cc_is_missing -v`: PASS，2 tests passed。
- `python -B -m unittest validation.tools.test_auto_migrate validation.tools.test_validate_auto_translation_evidence -v`: PASS，127 tests passed in 139.828s。
- `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-full-regression.ps1 -Rounds 1`: PASS，run id `20260627T003504Z`，35/35 steps passed，包含 `flashdb-release-stress-all` 10000 loops、`openspec validate --all` 和 `git diff --check`。

当前边界：
- 可以说：这轮修复的是已接受 FlashDB L3 evidence package 的 metadata/hash drift，以及 Windows 单测 fake compiler 的 harness 稳定性。
- 不应说：这轮新增了任何 C-to-Rust 翻译语义、扩大了 FlashDB L3 行为覆盖，或重新生成了完整 FlashDB L3 evidence package。
- 子线程额外发现 `legacy_incomplete` 的 `kvdb-lifecycle` 和 `tsdb-append-query-status` summary 仍有 stale hash；它们当前不参与 strict passed-summary validator gate，本轮不顺手改。
- 子线程还发现 `kvdb-compact-overwrite` 的部分 manifest-like input bindings 与当前工作区源码 hash 不一致；这说明旧 evidence 可以自洽通过当前 strict gate，但若要证明“基于最新 workspace 重新生成”，后续应重跑该 L3 evidence package，而不是只改声明 hash。
- 工作树里仍有大量 `validation/evidence/demo`、`validation/evidence/l2-slices`、`validation/evidence/libuv` 的既有 EOL/dirty 噪声；提交时必须继续使用白名单，不能 stage/revert 无关 evidence 文件。

English mirror summary:

- This slice fixes validation-chain stability only. It does not add translation capability or expand the FlashDB L3 behavioral boundary.
- `l3-kvdb-compact-overwrite-summary.json` now binds four stale evidence `sha256` fields to the current evidence files: `c_oracle`, `c_oracle_producer_evidence`, `mutated_value_or_entries_oracle`, and `summary_md`.
- Windows fake compiler tests no longer copy interactive `cmd.exe` as the produced harness executable. They copy `System32/hostname.exe` instead, giving a stable zero-exit executable for harness execution checks.
- Focused FlashDB L3 validation passed, the full auto-migrate unittest pair passed with 127 tests, and full regression run `20260627T003504Z` passed all 35 steps including release stress, OpenSpec validation, and `git diff --check`.
- Legacy-incomplete FlashDB summaries still have stale hashes and are intentionally not changed in this slice because they are outside the current strict passed-summary gate.
- The accepted `kvdb-compact-overwrite` evidence is self-consistent under the current validator, but some manifest-like input bindings do not match the latest workspace source hashes. Regenerate the L3 evidence package later if the claim needs to be “freshly generated from current workspace” rather than “current accepted package remains validator-consumable.”

## 95. 2026-06-27 scalar bitwise OR and left shift through typed IR and clang lowering

本轮继续按多智能体并行推进核心翻译切口。只读子线程分别复核了 typed IR / clang lowering 改动风险、双语文档同步点和提交前验证边界；主线程按 TDD 把窄化标量整数 bitwise OR `|` 与 left shift `<<` 接入 `GenericTypedIr` candidate generation。结论：这是通用 typed IR scalar expression 能力，不是 FlashDB 专用代码，也不是 semantic acceptance。

核心改动：

- `crates/c2r-translator/src/typed_ir.rs`
  - `IrBinOp::BitOr` 现在发射 Rust `|`。
  - `IrBinOp::Shl` 现在发射 Rust `<<`。
  - `|` 沿用同类型标量整数规则，要求 lhs/rhs/result 三者类型一致。
  - `<<` 沿用 shift 规则，要求 lhs/result 类型一致；本轮没有建模 rhs shift count 合法性或完整 C shift UB。
- `crates/c2r-translator/src/clang_frontend.rs`
  - 新增 `ClangBinaryOperator::BitOr` 和 `ClangBinaryOperator::Shl`。
  - AST opcode `"|"` / `"<<"` 会进入 skeleton。
  - cast-preservation 和 lowering 都映射到 `IrBinOp::BitOr` / `IrBinOp::Shl`。
  - 新增 opcode mapping 单元测试，并补 `|` operand 的 `int -> uint32_t` implicit integral cast preservation 回归测试。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 direct typed IR 正向测试 `typed_ir_emits_scalar_bit_or_and_left_shift`。
  - 新增 clang skeleton lowering 测试 `typed_ir_emits_scalar_bit_or_and_left_shift_from_clang_lowered_ir`。
  - 新增 clang skeleton 回归测试 `typed_ir_emits_left_shift_with_int_shift_count_from_clang_lowered_ir`，覆盖真实 clang 常见的 `uint32_t value << 4` 中 rhs shift count 为 `int` literal 的形态。
  - 新增 gated real clang smoke `clang_ast_dump_emits_bit_or_and_left_shift_when_enabled`。
- 双语文档已同步：
  - `docs/c2rust-migration-agent/README.md`
  - `docs/c2rust-migration-agent/README.en.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.en.md`
  - `docs/superpowers/specs/2026-06-27-candidate-route-p0-design.md`
  - `docs/superpowers/specs/2026-06-27-candidate-route-p0-design.en.md`

已确认红灯：

```powershell
cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features typed-ir typed_ir_emits_scalar_bit_or_and_left_shift -- --nocapture
cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-lowering-report typed_ir_emits_scalar_bit_or_and_left_shift_from_clang_lowered_ir -- --nocapture
```

红灯表现：

- direct typed IR 失败于 `stmt[0].return expr binary op BitOr is unsupported`。
- clang skeleton 测试在实现前编译失败，提示 `ClangBinaryOperator` 没有 `Shl` / `BitOr` variant。

已跑过的聚焦绿灯：

```powershell
cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features typed-ir typed_ir_emits_scalar_bit_or_and_left_shift -- --nocapture
cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-lowering-report typed_ir_emits_scalar_bit_or_and_left_shift_from_clang_lowered_ir -- --nocapture
cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-lowering-report typed_ir_emits_left_shift_with_int_shift_count_from_clang_lowered_ir -- --nocapture
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-lowering-report --test bounded_translation clang_ast_dump_emits_bit_or_and_left_shift_when_enabled -- --nocapture
cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-lowering-report expr_skeleton_from_ast_maps_bitwise_or_and_left_shift_opcodes -- --nocapture
cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-lowering-report expr_skeleton_from_ast_preserves_integer_implicit_casts_for_bitwise_or_operands -- --nocapture
cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-lowering-report bit_or_and_left_shift -- --nocapture
```

聚焦结果：

- direct typed IR 正向测试通过，并生成可 rustc 编译的 `return ((value << 4u32) | 3u32);`。
- clang skeleton lowering 测试通过。
- real clang AST smoke 在 `C2R_RUN_CLANG_AST_TESTS=1` 且 `CLANG_PATH=C:\Program Files\LLVM\bin\clang.exe` 时实际运行并通过。
- opcode mapping 单元测试通过。
- `uint32_t << int` shift-count skeleton 回归测试通过，锁住真实 clang AST 常见 rhs 类型。
- `|` operand implicit integral cast preservation 单元测试通过。
- `bit_or_and_left_shift` filter 下的 3 个聚焦测试通过；其中 gated real clang smoke 在未设置环境变量的 grouped run 中会按设计跳过，实际执行结果以上面的单独 env smoke 为准。

提交前最终验证结果：

- `cargo fmt --manifest-path .\crates\c2r-translator\Cargo.toml -- --check`: PASS。
- `cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features typed-ir`: PASS，141 个 bounded translation tests 通过。
- `cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend`: PASS，44 个 bounded translation tests 通过。
- `cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features typed-ir,clang-frontend`: PASS，25 个 lib tests + 241 个 bounded translation tests 通过。
- `cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-lowering-report`: PASS，29 个 lib tests + 242 个 bounded translation tests 通过。
- `cargo clippy --manifest-path .\crates\c2r-translator\Cargo.toml --all-targets --features clang-lowering-report -- -D warnings`: PASS。
- `openspec validate --all --strict`: PASS，37 items passed。
- `git diff --check -- <本轮白名单文件>`: PASS；Windows 工作树仍打印 LF/CRLF replacement warnings，但没有 whitespace error。
- 没有在主工作树跑 `scripts/run-full-regression.ps1`，因为当前已有大量既有 `validation/evidence/**` dirty/EOL 噪声，且该脚本包含会刷新 evidence 的步骤；本轮以 translator feature suite、real clang smoke、clippy、OpenSpec 和白名单 diff check 作为提交前验证。

当前边界：

- 可以说：direct typed IR、clang skeleton 和真实 clang AST smoke 覆盖的窄化标量整数 `|` / `<<` 现在能进入 `GenericTypedIr` 并生成可编译 Rust candidate。
- 可以说：这是候选生成能力，`semantic_pass` 仍必须保持 `false`，最终接受仍属于 C oracle、Rust replay、schema diff、negative diff、unsafe ledger 和 final verification。
- 不应说：已经支持完整 C bitwise/shift semantics、usual arithmetic conversions、无效 shift count、signed shift/overflow UB parity、指针算术或 semantic acceptance。
- 历史说明：本节写作时尚未实现 L0 0-token deterministic route；第 96 节已把 scalar-only `GenericTypedIr` candidate 的 `candidate_route.token_cost=0` 接入 L0 route signal，后续以第 96 节为准。
- FlashDB 仍只是用例；本轮没有恢复任何 crc32 专用 route、typed IR crc32 matcher 或 canned template。
- 工作树里仍有大量既有 `validation/evidence/**` dirty/EOL 噪声；提交必须继续使用白名单，不可 stage/revert 无关 evidence 文件。
- 本节更新当前能力状态；早期章节中“不要顺手实现 `<<`、`|`”的限制只针对当时 shift-right 切口，已经被本节的 TDD 切片 supersede。

下一步建议：

- 完成本轮最终验证、白名单提交并推送。
- 后续核心切口优先做 cast/usual-conversion 分类；L0 `token_cost=0` 路由规则已由第 96 节实现。不要把 short-circuit、pointer/null comparison 或完整 C shift 语义混入 bitwise/shift 切片。

English mirror summary:

- Narrow scalar integer bitwise OR `|` and left shift `<<` now flow through direct typed IR, clang skeleton lowering, and a real clang AST smoke test into `GenericTypedIr` and compilable Rust candidates.
- `IrBinOp::BitOr` emits `|`; `IrBinOp::Shl` emits `<<`.
- `ClangBinaryOperator::{BitOr, Shl}` map AST opcodes `"|"` and `"<<"` into typed IR.
- This is candidate generation only and must keep `semantic_pass=false`.
- It does not support full C bitwise/shift semantics, usual arithmetic conversions, invalid shift counts, signed shift/overflow UB parity, pointer arithmetic, or semantic acceptance.
- Historical note: when this section was written, the L0 `token_cost=0` deterministic route was still a future router slice. Section 96 has since wired scalar-only `GenericTypedIr` candidates with `candidate_route.token_cost=0` into the L0 route signal.
- FlashDB remains only a use case. This slice does not restore any crc32-specific route, typed IR crc32 matcher, or canned template.
