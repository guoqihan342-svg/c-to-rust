## 96. 2026-06-27 L0 zero-token deterministic typed IR route signal

本轮继续按多智能体并行推进。只读子线程分别复核了 L0/L1 router 现状、cast/usual-conversion 后续切口，以及文档/验证影响；主线程按 TDD 把 scalar-only `GenericTypedIr` + `token_cost=0` candidate 接入 L0 deterministic route signal。结论：这是 route/cost/provenance 分类，不是 semantic acceptance；第 95 节里“L0 `token_cost=0` 仍是 future”的说法被本节 supersede。

核心改动：

- `validation/tools/auto_migrate.py`
  - `route_level()` 现在先读取 `pointer_nodes`，并把 `scalar_only=not pointer_nodes` 传给 `typed_ir_candidate_route_signal()`。
  - `typed_ir_candidate_route_signal()` 只在 `status=generated`、`route=GenericTypedIr`、`rust_draft_generated=true`、`scalar_only=true` 且 `candidate_route.token_cost == 0` 时返回 L0。
  - `token_cost` 缺失或非 0 的 `GenericTypedIr` 仍走 L1。
  - 有 pointer surface 的 `GenericTypedIr` 仍至少是 L1。
  - `alias_blocked`、`requires_noalias_contract`、`unknown_alias` 和 unknown pointer ownership floor 仍优先，分别保持 L3/L2，不会被 L0 route signal 覆盖。
- `validation/tools/test_auto_migrate.py`
  - 把原 `test_generated_typed_ir_candidate_is_l1_route_signal` 改为 `test_generated_zero_token_scalar_typed_ir_candidate_routes_l0`，先确认红灯：旧逻辑返回 L1。
  - 新增 `test_scalar_typed_ir_candidate_without_zero_token_cost_stays_l1` 和 `test_scalar_typed_ir_candidate_with_nonzero_token_cost_stays_l1`，锁住缺失或非 0 token cost 不走 L0。
  - 在 `test_route_and_profile_bind_clang_lowered_typed_ir_candidate_evidence` 中确认 FlashDB 这类 pointer-bearing `GenericTypedIr + token_cost=0` 仍是 L1。
  - 保留 alias risk / blocked alias / unsupported typed IR 测试，并新增 unknown pointer ownership 测试，分别证明 L2/L3/L2/L2 边界未被破坏。
- 双语文档与 OpenSpec 已同步：
  - `docs/c2rust-migration-agent/README.md`
  - `docs/c2rust-migration-agent/README.en.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.en.md`
  - `docs/superpowers/specs/2026-06-27-candidate-route-p0-design.md`
  - `docs/superpowers/specs/2026-06-27-candidate-route-p0-design.en.md`
  - `validation/README.md`
  - `validation/gates.md`
  - `validation/auto-translation-template/README.md`
  - `openspec/specs/bounded-auto-translation-pipeline/spec.md`

已确认红灯：

```powershell
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_generated_zero_token_scalar_typed_ir_candidate_routes_l0 -v
```

红灯表现：旧逻辑返回 `L1`，测试期望 `L0`，失败于 `AssertionError: 'L1' != 'L0'`。

已跑过的聚焦绿灯：

```powershell
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_generated_zero_token_scalar_typed_ir_candidate_routes_l0 validation.tools.test_auto_migrate.AutoMigrateTests.test_generated_typed_ir_candidate_with_alias_risk_routes_l2_not_l1 validation.tools.test_auto_migrate.AutoMigrateTests.test_generated_typed_ir_candidate_does_not_override_blocked_alias_route validation.tools.test_auto_migrate.AutoMigrateTests.test_unsupported_typed_ir_candidate_preserves_reason_and_routes_l2 -v
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_route_and_profile_bind_clang_lowered_typed_ir_candidate_evidence validation.tools.test_auto_migrate.AutoMigrateTests.test_generated_zero_token_scalar_typed_ir_candidate_routes_l0 validation.tools.test_auto_migrate.AutoMigrateTests.test_scalar_typed_ir_candidate_without_zero_token_cost_stays_l1 validation.tools.test_auto_migrate.AutoMigrateTests.test_scalar_typed_ir_candidate_with_nonzero_token_cost_stays_l1 validation.tools.test_auto_migrate.AutoMigrateTests.test_generated_typed_ir_candidate_with_unknown_pointer_role_routes_l2_not_l0 validation.tools.test_auto_migrate.AutoMigrateTests.test_generated_typed_ir_candidate_with_alias_risk_routes_l2_not_l1 validation.tools.test_auto_migrate.AutoMigrateTests.test_generated_typed_ir_candidate_does_not_override_blocked_alias_route validation.tools.test_auto_migrate.AutoMigrateTests.test_unsupported_typed_ir_candidate_preserves_reason_and_routes_l2 -v
```

聚焦结果：新增后 8 个 route boundary tests 均通过。

当前边界：

- 可以说：scalar-only、`GenericTypedIr`、`candidate_route.token_cost=0`、`rust_draft_generated=true` 的 deterministic candidate 现在能记录为 `route_decision.level=L0`。
- 可以说：这是 candidate route / context budget / provenance classification，只影响候选路径和验证 profile 分层。
- 不应说：L0 route 证明 semantic equivalence，或 rustc pass + token_cost=0 就 accepted。
- 不应说：zero-token deterministic route 可以绕过 C oracle、Rust replay、schema-aware diff、negative diff、unsafe evidence、cache/version binding 或 final verification。
- `semantic_pass=false` 和 `generated_draft_semantic_pass=false` 仍保持到独立 validation gates 接受 exact draft。
- catalog validation 的 L0 和 auto-translation `route_decision.level=L0` 是不同概念，不能互相替代。

下一步建议：

- 完成本轮最终验证、白名单提交并推送。
- 历史说明：本节写作时 comparison operand integral cast 仍是下一步；第 97 节已窄化放开 clang/type-map 已证明的 integer cast operand，覆盖真实 `uint32_t value; if (value > 0)` 形态，但仍不是完整 usual arithmetic conversions。

English mirror summary:

- Scalar-only `GenericTypedIr` candidates with `candidate_route.token_cost=0` and a generated Rust draft now route as `route_decision.level=L0`.
- This is deterministic candidate routing / context-budget provenance only. Generated Rust remains candidate evidence.
- `semantic_pass=false` and `generated_draft_semantic_pass=false` remain until independent validation gates accept the exact draft.
- Pointer-bearing `GenericTypedIr` candidates remain at least L1; alias blocked, requires-noalias, unknown alias, and unknown pointer ownership floors still override to L3/L2.
- Catalog L0 and auto-translation `route_decision.level=L0` are different evidence concepts.
- The next high-value core slice is narrow integral-cast support for comparison operands, not full usual arithmetic conversions.

## 97. 2026-06-27 narrow integral cast comparison operands

本轮继续按多智能体并行推进。只读子线程分别复核了 typed IR comparison emitter、clang lowering/真实 clang smoke，以及中英文文档 stale 边界；主线程按 TDD 把 comparison operand 上的窄化整数 cast 从 fail-closed 改成 deterministic candidate generation。结论：这只覆盖 clang/type-map 已证明的 integer cast operand，不是完整 usual arithmetic/scalar conversions，也不是 semantic acceptance。

核心改动：

- `crates/c2r-translator/src/typed_ir.rs`
  - `validate_comparison_condition_types()` 不再无条件拒绝顶层 `IrExpr::Cast`。
  - 新增 `validate_comparison_cast_operand()`：只有 cast source 和 target 都是当前 emitter 可发射的整数 scalar type 时才允许继续。
  - cast 后两侧 operand 仍必须通过既有 `expr_type()` / `emit_scalar_type()` 完全同型检查，例如 `u32 > (0i32 as u32)` 可发射。
  - 非整数 cast、unsupported type、pointer/float comparison、call/inc/dec/deref side-effect operand、short-circuit `&&` / `||`、非 C `int` result type 和未建模 mixed-width conversion 仍 fail closed。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 将旧的 fail-closed 测试改为正向测试：
    - `typed_ir_emits_comparison_condition_with_integral_cast_operand`
    - `typed_ir_emits_value_comparison_with_integral_cast_operand_as_c_int`
  - 两个测试都确认生成 `(0i32 as u32)`，并通过 `rustc` smoke。
  - 新增 `typed_ir_rejects_comparison_with_non_integer_cast_operand`，锁住非整数 cast source 仍 fail closed。
- 文档同步：
  - `docs/c2rust-migration-agent/README.md`
  - `docs/c2rust-migration-agent/README.en.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.en.md`
  - `docs/superpowers/specs/2026-06-27-candidate-route-p0-design.md`
  - `docs/superpowers/specs/2026-06-27-candidate-route-p0-design.en.md`

已确认红灯：

```powershell
cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features typed-ir integral_cast_operand -- --nocapture
```

红灯表现：旧 production 仍报 `comparison rhs cast operand is unsupported until usual conversions are modeled`，两个新增正向测试均失败。

已跑过的聚焦绿灯：

```powershell
cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features typed-ir integral_cast_operand -- --nocapture
cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features typed-ir non_integer_cast -- --nocapture
cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features typed-ir comparison -- --nocapture
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir --test bounded_translation clang_ast_dump_emits_unsigned_comparison_if_condition_when_enabled -- --nocapture
```

聚焦结果：

- `integral_cast_operand` filter 下 2 个测试通过。
- `non_integer_cast` filter 下 1 个 fail-closed 测试通过。
- `comparison` filter 下 32 个 typed IR comparison tests 通过。
- 真实 clang gated smoke `clang_ast_dump_emits_unsigned_comparison_if_condition_when_enabled` 通过。

提交前最终验证结果：

- `cargo fmt --manifest-path .\crates\c2r-translator\Cargo.toml -- --check`: PASS。
- `openspec validate --all --strict`: PASS，37 items passed。
- `git diff --check -- <本轮白名单文件>`: PASS；Windows 工作树仍打印 LF/CRLF replacement warnings，但没有 whitespace error。
- `cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features typed-ir`: PASS，142 bounded translation tests 通过。
- `cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir`: PASS，25 个 lib tests + 242 个 bounded translation tests 通过。
- `cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-lowering-report`: PASS，29 个 lib tests + 243 个 bounded translation tests 通过。
- `cargo clippy --manifest-path .\crates\c2r-translator\Cargo.toml --all-targets --features clang-lowering-report -- -D warnings`: PASS。

当前边界：

- 可以说：comparison condition 和 value-position C `int` 0/1 materialization 现在可处理 source/target 都是可发射整数类型、且 cast 后两侧类型完全一致的 integral cast operand。
- 可以说：真实 clang 已保留 `uint32_t value; if (value > 0)` 的 RHS `IntegralCast`，typed IR emitter 现在能生成 `if (value > (0i32 as u32)) {`。
- 不应说：已经支持完整 C usual arithmetic conversions、完整 mixed-width/unsigned conversions、pointer comparison、float comparison、side-effect operand、short-circuit logic 或 semantic acceptance。
- FlashDB 仍只是用例；本轮没有恢复任何 crc32 专用 route、typed IR crc32 matcher 或 canned template。
- 工作树里仍有大量既有 `validation/evidence/**` dirty/EOL 噪声；提交必须继续使用白名单，不可 stage/revert 无关 evidence 文件。

下一步建议：

- 跑真实 clang gated smoke：`clang_ast_dump_emits_unsigned_comparison_if_condition_when_enabled`。
- 完成本轮最终验证、白名单提交并推送。
- 后续核心切口可以继续做 explicit usual-conversion 分类，但不要把 pointer/null comparison、short-circuit 或完整 C arithmetic semantics 混入这刀。

English mirror summary:

- Narrow integral-cast comparison operands now emit through generic typed IR when cast source and target are supported integer scalar types and the post-cast operand types match exactly.
- This unlocks real clang `uint32_t value; if (value > 0)` lowering into `if (value > (0i32 as u32)) {`.
- This remains candidate generation only and keeps `semantic_pass=false`.
- It is not full usual arithmetic/scalar conversion support. Pointer/floating-point comparisons, unmodeled mixed-width conversions, side-effect operands, short-circuit logic, and semantic acceptance still fail closed.

## 98. 2026-06-27 readonly pointer NULL presence candidate

本轮继续按多智能体并行推进。只读子线程分别复核了 binary cast operand、pointer/null comparison、logical `&&`/`||`、赋值/复合赋值、pointer/index lowering 和文档边界；主线程按 TDD 选择了最小可落地的 readonly pointer NULL presence 切片。结论：FlashDB 仍只是用例，本切片不是 crc32 专用代码，也不是完整 pointer comparison；它只把真实 clang 中常见的 `const int *values; return values != NULL;` 这类 presence check 从 fail-closed 推进到 `GenericTypedIr` candidate。

核心改动：
- `crates/c2r-translator/src/typed_ir.rs`
  - 新增 `IrExpr::NullPtr`，作为 typed IR 的 null pointer literal。
  - `EmitContext` 新增 `nullable_pointer_params`，只在参数是 readonly integer pointer 且只出现在直接 `== NULL` / `!= NULL` comparison 时启用。
  - nullable 参数发射为 `Option<&[T]>`；`ptr == NULL` 发射 `.is_none()`，`ptr != NULL` 发射 `.is_some()`。
  - 如果同一个 nullable pointer 参数在 null check 后继续出现在 index/deref/普通表达式中，直接 fail closed，避免生成 `Option<&[T]>` 后又写出 `values[0]` 这种错误 Rust。
  - pointer-pointer comparison、非 readonly integer pointer、pointer truthiness、任意 pointer relational comparison、null check 后流敏 unwrap、deref/index 使用、call/inc/dec side-effect operand 继续 fail closed。
- `crates/c2r-translator/src/clang_frontend.rs`
  - `ClangExprSkeleton` 新增 `NullPtr`。
  - `ImplicitCastExpr` / `CStyleCastExpr` 的 `castKind=NullToPointer` 且 operand 为整数 0 时，lower 成 typed IR null pointer literal。
  - 真实 clang 对 `NULL` 宏会产生 `CStyleCastExpr NullToPointer`，本轮 real clang smoke 覆盖了这条路径。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 direct typed IR 正测：
    - `typed_ir_emits_value_comparison_with_null_pointer_operand`
    - `typed_ir_emits_comparison_condition_with_null_pointer_operand`
  - 新增 fail-closed 负测：
    - `typed_ir_rejects_nullable_pointer_use_after_null_check`
  - 新增真实 clang gated smoke：
    - `clang_ast_dump_emits_null_pointer_comparison_return_value_when_enabled`
- 文档同步：
  - `docs/c2rust-migration-agent/README.md`
  - `docs/c2rust-migration-agent/README.en.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.en.md`
  - `docs/superpowers/specs/2026-06-27-candidate-route-p0-design.md`
  - `docs/superpowers/specs/2026-06-27-candidate-route-p0-design.en.md`

已确认红灯：

```powershell
cargo test --features typed-ir null_pointer
```

红灯表现：测试期望 `IrExpr::NullPtr`，旧代码编译失败于 `no variant named NullPtr found for enum IrExpr`。

已跑过的聚焦绿灯：

```powershell
cargo test --features typed-ir null_pointer
cargo test --features typed-ir nullable_pointer
cargo test --features "typed-ir clang-frontend" null_to_pointer
cargo test --features "typed-ir clang-frontend" null_pointer
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:/Program Files/LLVM/bin/clang.exe'; cargo test --features "typed-ir clang-frontend" clang_ast_dump_emits_null_pointer_comparison_return_value_when_enabled -- --nocapture
```

聚焦结果：
- `null_pointer` direct/gated 编译路径通过。
- `nullable_pointer` fail-closed 负测通过。
- clang skeleton `NullToPointer` lowering 单测通过。
- 真实 clang AST smoke 实际运行通过；真实 `NULL` 宏路径是 `CStyleCastExpr NullToPointer`。

当前边界：
- 可以说：readonly integer pointer 参数的直接 `== NULL` / `!= NULL` presence check 现在可以进入 `GenericTypedIr` 并生成可编译 Rust candidate。
- 可以说：该参数会变成 `Option<&[T]>`，presence check 会变成 `.is_none()` / `.is_some()`。
- 不应说：已经支持完整 pointer comparison、pointer truthiness、null check 后流敏 unwrap、nullable slice indexing、mutable pointer、pointer arithmetic、alias semantics 或 semantic acceptance。
- `semantic_pass=false` 仍保持到独立 validation gates 接受 exact draft。
- 工作树里仍有大量既有 `validation/evidence/**` dirty/EOL 噪声；提交必须继续使用白名单，不可 stage/revert 无关 evidence 文件。

下一步建议：
- 继续最终验证、白名单提交并推送本切片。
- 后续核心切片优先级可按子线程结论排：readonly pointer deref read `*p -> p[0]`、简单标量 compound assignment `+=` lowering、`&&`/`||` 短路逻辑窄化支持、binary cast operand 默认覆盖测试/real clang smoke。
- 对 `codex/translator-strengthening-analysis.md` 的方案评价：它的“验证体系强、翻译器能力追不上”判断仍有道理，但其中“先装 clang / typed IR 指针类型基础不足”的部分已被本分支后续进展部分 supersede；后续应把方案里的 P0 改成继续扩 typed IR emitter 的泛化子集，而不是回到 raw string recipe。

English mirror summary:

- Added a narrow readonly pointer NULL-presence typed IR candidate path.
- `NullToPointer` casts from clang now lower into `IrExpr::NullPtr`.
- `const int *values; return values != NULL;` emits as `pub fn has_values(values: Option<&[i32]>) -> i32` plus `values.is_some()`.
- Nullable pointer parameters are allowed only in direct `== NULL` / `!= NULL` comparisons; use after the null check still fails closed.
- This remains candidate generation only and keeps `semantic_pass=false`.
- It is not arbitrary pointer comparison, pointer truthiness, flow-sensitive unwrap, nullable indexing, pointer arithmetic, alias semantics, or semantic acceptance.

## 99. 2026-06-27 readonly pointer direct deref read candidate

本轮继续按多智能体并行推进。只读子线程分别调查了 readonly pointer deref、typed IR compound assignment、`&&`/`||` 短路逻辑和路线文档一致性；主线程按 TDD 选择最小核心翻译切片：readonly integer pointer direct dereference read。结论：`*p` 现在可作为无副作用标量读进入 `GenericTypedIr` candidate，但这不是 `*(p+i)`、mutable pointer、pointer write、alias semantics 或 semantic acceptance。

核心改动：
- `crates/c2r-translator/src/typed_ir.rs`
  - 新增 `emit_readonly_pointer_deref_expr()`。
  - `IrExpr::Deref { ptr: Var(p), ty }` 在 `p` 是已声明 readonly integer pointer 时发射为 `p[0usize]`。
  - `emit_expr_with_prelude()` 保留 `*p++` byte cursor 特例；只有非 `IncDec` deref 才走 direct readonly deref helper，避免削弱既有 post-increment fail-closed 诊断。
  - nullable pointer param 仍不能 deref；`NULL` presence check 后继续 deref/index 仍 fail closed。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 helper `ir_deref()`。
  - 新增 direct typed IR 正测：
    - `typed_ir_emits_readonly_pointer_deref_read_as_slice_zero_index`
    - `typed_ir_emits_value_comparison_with_readonly_pointer_deref_operand_as_c_int`
    - `typed_ir_emits_comparison_condition_with_readonly_pointer_deref_operand`
    - `typed_ir_emits_logical_not_value_with_readonly_pointer_deref_operand`
  - 新增真实 clang gated smoke：
    - `clang_ast_dump_emits_pointer_deref_return_value_when_enabled`
  - 旧 deref 负测仍保留 fail-closed，但现在锁定的是未声明/未建模 deref 仍拒绝，而不是所有 deref 都拒绝。
- 文档同步：
  - `codex/translator-strengthening-analysis.md`
  - `codex/translator-strengthening-analysis.en.md`
  - `docs/c2rust-migration-agent/README.md`
  - `docs/c2rust-migration-agent/README.en.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.en.md`
  - `docs/superpowers/specs/2026-06-27-candidate-route-p0-design.md`
  - `docs/superpowers/specs/2026-06-27-candidate-route-p0-design.en.md`
- 验证流水线修复：
  - 修复 `validation/evidence/demo/auto-translation/sum-i32-ptr-arith/**` 和 `validation/evidence/demo/auto-translation/call-expression/**` 中 stale accepted c_oracle sha256；这些字段指向的 accepted oracle 文件真实 hash 分别是 `b48e57...` 和 `cc00fb...`，旧值会让 `validate_auto_translation_evidence.py --require-semantic-pass` 在 schema/negative-diff gate 之前先失败。

已确认红灯：

```powershell
cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features typed-ir typed_ir_emits_readonly_pointer_deref_read_as_slice_zero_index -- --nocapture
```

红灯表现：旧 production 报 `stmt[0].return expr deref expression is unsupported`。

已跑过的聚焦绿灯：

```powershell
cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features typed-ir typed_ir_emits_readonly_pointer_deref_read_as_slice_zero_index -- --nocapture
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:/Program Files/LLVM/bin/clang.exe'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features "typed-ir clang-frontend" pointer_deref -- --nocapture
cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features typed-ir deref -- --nocapture
```

聚焦结果：
- direct readonly `*p` red/green 测试通过。
- `pointer_deref` filter 下 4 条测试通过：clang skeleton lowering、真实 clang lowering、direct typed IR emit、真实 clang emit。
- `deref` filter 下 7 条测试通过：direct read、comparison value-position、comparison condition、logical-not value-position 和三个 fail-closed 负测。

当前边界：
- 可以说：readonly integer pointer direct `*p` 现在发射为 Rust slice 0 下标，并可作为普通标量读参与 comparison/logical-not candidate generation。
- 不应说：已经支持 `*(p+i)`、pointer arithmetic、nullable pointer deref、mutable pointer、pointer write、pointer truthiness、任意 pointer comparison、alias semantics 或 semantic acceptance。
- `semantic_pass=false` 仍保持到独立 validation gates 接受 exact draft。

下一步建议：
- 跑完整门禁、白名单提交并推送本切片。
- 后续核心切片优先级：`*(p+i)` bounded pointer arithmetic read、typed IR first-class scalar compound assignment、condition-position `&&` / `||`、usual conversion 分类。

English mirror summary:

- Added narrow readonly pointer direct dereference read candidate generation.
- `const uint8_t *p; return *p;` now emits as `pub fn read_byte(p: &[u8]) -> u8 { return p[0usize]; }`.
- Direct readonly deref reads can also act as ordinary scalar operands in comparison/logical-not candidate generation, for example `*p == 0` and `!*p`.
- `*p++` byte cursor behavior remains on its prelude path; nullable pointer deref, `*(p+i)`, mutable pointer, pointer writes, pointer truthiness, arbitrary pointer comparison, alias semantics, and semantic acceptance still fail closed.

## 100. 2026-06-27 readonly bounded pointer offset-deref read candidate

本轮继续按多智能体并行推进。只读子线程分别复核了真实 clang AST 里的 `*(p+i)` 形态、typed IR emitter 边界、测试缺口和文档同步范围；主线程按 TDD 选择最小核心翻译切片：readonly integer pointer 的 bounded offset-deref read。结论：`*(p+i)` / `*(i+p)` 现在可作为无副作用标量读进入 `GenericTypedIr` candidate，并发射为 Rust slice index；这不是任意 pointer arithmetic、pointer write、alias semantics 或 semantic acceptance。

核心改动：
- `crates/c2r-translator/src/typed_ir.rs`
  - `emit_readonly_pointer_deref_expr()` 先识别 `Deref(Binary(Add, base, index))`。
  - 新增 `emit_readonly_pointer_add_deref_expr()` 和 `readonly_pointer_add_operands()`，只接受 readonly integer pointer base + integer index，并支持 `p+i` / `i+p`。
  - 新增 `validate_readonly_pointer_add_index_expr()`，index 只允许整数变量、整数字面量和整数 cast；call、inc/dec、deref、compound expression、unary、index、address-of、null pointer、array literal 和 unsupported expression 都 fail closed。
  - nullable pointer param、mutable pointer、base 未声明、pointer add result type 与 base type 不一致、deref result type 与 pointee element type 不一致继续 fail closed。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 direct typed IR 正测：
    - `typed_ir_emits_readonly_pointer_add_index_deref_read`
    - `typed_ir_emits_readonly_index_add_pointer_deref_read`
    - `typed_ir_emits_readonly_pointer_add_literal_deref_read`
    - `typed_ir_emits_value_comparison_with_readonly_pointer_add_index_deref_operand_as_c_int`
    - `typed_ir_emits_comparison_condition_with_readonly_pointer_add_index_deref_operand`
    - `typed_ir_emits_logical_not_value_with_readonly_pointer_add_index_deref_operand`
    - `typed_ir_emits_logical_not_condition_with_readonly_pointer_add_index_deref_operand`
  - 新增 fail-closed 负测：
    - `typed_ir_rejects_mutable_pointer_add_index_deref_read`
    - `typed_ir_rejects_readonly_pointer_add_call_index_deref_read`
    - `typed_ir_rejects_readonly_pointer_add_compound_index_deref_read`
    - `typed_ir_rejects_logical_not_condition_with_readonly_pointer_add_compound_index_deref_operand`
  - 新增 clang skeleton / real clang smoke：
    - `clang_lowering_skeleton_maps_pointer_add_deref_expr`
    - `clang_ast_dump_emits_pointer_add_deref_return_values_when_enabled`
    - `clang_ast_dump_emits_pointer_add_deref_logical_not_if_condition_when_enabled`
- 文档同步：
  - `codex/translator-strengthening-analysis.md`
  - `codex/translator-strengthening-analysis.en.md`
  - `docs/c2rust-migration-agent/README.md`
  - `docs/c2rust-migration-agent/README.en.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.en.md`
  - `docs/superpowers/specs/2026-06-27-candidate-route-p0-design.md`
  - `docs/superpowers/specs/2026-06-27-candidate-route-p0-design.en.md`

已确认红灯：

```powershell
cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features typed-ir typed_ir_emits_readonly_pointer_add_index_deref_read -- --nocapture
```

红灯表现：旧 production 报 `stmt[0].return expr deref pointer must be Var`。

已跑过的聚焦绿灯：

```powershell
cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features typed-ir pointer_add -- --nocapture
cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features "typed-ir clang-frontend" pointer_add_deref -- --nocapture
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features "typed-ir clang-frontend" pointer_add_deref -- --nocapture
```

聚焦结果：
- `pointer_add` filter 下 10 条测试通过：return、literal offset、`i+p` commuted、comparison value-position、comparison condition、logical-not value-position、logical-not condition，以及 mutable/call/compound index fail-closed。
- `pointer_add_deref` filter 下 3 条 clang 测试通过；真实 clang AST gate 打开后同 3 条实际运行通过，覆盖 `read_pi`、`read_ip`、`read_p1` 和 `if (!*(p+i))`。

当前边界：
- 可以说：readonly integer pointer 的 bounded `*(p+i)` / `*(i+p)` read 现在发射为 Rust slice index，并可作为普通标量读参与 comparison/logical-not candidate generation。
- 不应说：已经支持任意 pointer arithmetic、pointer subtraction、array-to-pointer decay、nullable pointer deref/index、mutable pointer、pointer write、pointer truthiness、任意 pointer comparison、alias semantics 或 semantic acceptance。
- `semantic_pass=false` 仍保持到独立 validation gates 接受 exact draft。

下一步建议：
- 跑完整门禁、白名单提交并推送本切片。
- 后续核心切片优先级：typed IR first-class scalar compound assignment、condition-position `&&` / `||`、usual conversion 分类。

English mirror summary:

- Added narrow readonly bounded pointer offset-deref read candidate generation.
- `const uint8_t *p; return *(p+i);` now emits as `pub fn read_pi(p: &[u8], i: usize) -> u8 { return p[i as usize]; }`.
- The same support covers `*(i+p)`, literal offsets, comparison operands such as `*(p+i) == 0`, and logical-not operands such as `!*(p+i)`.
- Index expressions are deliberately narrow: only integer vars, integer literals, and integer casts are accepted; call, inc/dec, compound index expressions, mutable pointers, nullable pointer deref/index, pointer writes, arbitrary pointer arithmetic, alias semantics, and semantic acceptance still fail closed.

## 101. 2026-06-27 reviewer follow-up and evidence binding repair

中文摘要：

- 只读 code-review 子智能体复核后未发现实现层 Critical 问题，但建议把 fail-closed 边界测得更细。
- 已补充直接负测：
  - `typed_ir_rejects_nullable_readonly_pointer_add_index_deref_read`
  - `typed_ir_rejects_readonly_pointer_add_incdec_index_deref_read`
  - `typed_ir_rejects_readonly_pointer_add_deref_index_deref_read`
  - `typed_ir_rejects_readonly_pointer_add_unsupported_index_deref_read`
  - `typed_ir_rejects_readonly_pointer_add_result_type_mismatch`
  - `typed_ir_rejects_readonly_pointer_add_deref_result_type_mismatch`
- 注意：nullable pointer 的 offset deref 在 nullable-use validator 阶段更早被拒绝，错误是 `nullable pointer param p is only supported in null comparisons`，这是比 emitter 分支更保守的 fail-closed。
- 修复了 `sum-i32-ptr-arith` 与 `call-expression` 两个 demo auto-translation evidence 中 accepted artifact SHA 绑定漂移；没有采用 `auto_migrate --accept-existing-evidence` 对 `sum-i32-ptr-arith` 的重生成结果，因为当前 L2/noalias profile 会把它确定性降级为 `candidate_generated / semantic_pass=false`。

English mirror:

- A read-only reviewer subagent found no critical implementation defect, but asked for tighter fail-closed regression tests.
- Added direct negative tests for nullable base, inc/dec index, deref index, unsupported index, pointer-add result type mismatch, and deref result type mismatch.
- Nullable offset deref is rejected earlier by the nullable-use validator, before the pointer-offset-deref emitter runs.
- Repaired accepted artifact SHA bindings for the demo `sum-i32-ptr-arith` and `call-expression` evidence packages while preserving `semantic_pass=true`.

## 102. 2026-06-27 condition-position short-circuit through typed IR and clang lowering

本轮继续按多智能体并行推进核心翻译切口。只读线程分别复核了 `&&` / `||`、compound assignment 和 implicit integral cast 的当前缺口；主线程按 TDD 选择最小安全切片：只支持 `if` / `while` 条件位置的 C short-circuit `&&` / `||`。结论：这是通用 typed IR candidate generation 能力，不是 FlashDB 专用代码，也不是 semantic acceptance；value-position `return a && b`、assignment RHS 和 declaration initializer 仍 fail closed。

核心改动：
- `crates/c2r-translator/src/typed_ir.rs`
  - `emit_condition_expr()` 在 comparison fallback 前识别 `IrBinOp::LogAnd` / `IrBinOp::LogOr`。
  - 新增 `emit_short_circuit_condition_expr()`，要求 logical operator 结果类型是 C `int`。
  - 左右操作数递归复用 `emit_condition_expr()`，因此只继承当前已建模的整数 truthiness、comparison、logical-not、readonly deref 和 bounded offset-deref 条件子集。
  - `emit_expr()` / `emit_binary_op()` 没有放开 `LogAnd` / `LogOr`，所以 value-position 仍拒绝。
- `crates/c2r-translator/src/clang_frontend.rs`
  - `ClangBinaryOperator` 新增 `LogAnd` / `LogOr`。
  - clang `BinaryOperator` opcode `"&&"` / `"||"` 现在 lowering 到 `IrBinOp::LogAnd` / `IrBinOp::LogOr`。
  - logical op operands 保留 clang 已给出的 integral cast；不自行实现完整 usual conversions。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 direct typed IR 正测：
    - `typed_ir_emits_short_circuit_if_conditions`
    - `typed_ir_emits_short_circuit_while_condition_with_comparison_operands`
  - 新增 fail-closed 负测：
    - `typed_ir_rejects_short_circuit_condition_with_non_int_result_type`
  - 既有 value-position 负测 `typed_ir_rejects_value_comparison_short_circuit_ops` 保持通过。
  - 新增 clang skeleton / real clang smoke：
    - `clang_lowering_skeleton_maps_short_circuit_if_condition`
    - `clang_ast_dump_emits_short_circuit_if_condition_when_enabled`

已确认红灯：

```powershell
cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features typed-ir short_circuit -- --nocapture
cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features "typed-ir clang-frontend" short_circuit -- --nocapture
```

红灯表现：
- direct typed IR 失败于 `stmt[0].if condition binary op LogAnd is unsupported` / `stmt[0].while condition binary op LogOr is unsupported`。
- non-C-int result 负测先失败为普通 unsupported，而不是专门的 `short-circuit result type must be C int`。
- clang skeleton 测试编译失败于 `ClangBinaryOperator::LogAnd` 不存在。

已跑过的聚焦绿灯：

```powershell
cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features typed-ir short_circuit -- --nocapture
cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features "typed-ir clang-frontend" short_circuit -- --nocapture
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features "typed-ir clang-frontend" short_circuit -- --nocapture
```

聚焦结果：
- `typed-ir` 下 `short_circuit` filter 4 条通过。
- `typed-ir clang-frontend` 下 `short_circuit` filter 6 条通过。
- 真实 clang AST gate 打开后同 6 条实际运行通过，覆盖 `if (left && right)`。

当前边界：
- 可以说：direct typed IR、clang skeleton 和真实 clang AST smoke 覆盖的 condition-position `&&` / `||` 现在能进入 `GenericTypedIr` 并生成可编译 Rust candidate。
- 可以说：`if (left && right)` 生成 `if (left != 0i32 && right != 0i32)`；`while ((left < 3) || (right != 0))` 生成 Rust bool condition。
- 不应说：已经支持 value-position short-circuit、完整 usual scalar conversions、pointer truthiness、float truthiness、call/inc/dec/side-effect operand、函数指针、volatile/hardware register 或 semantic acceptance。
- `semantic_pass=false` 仍保持到独立 validation gates 接受 exact draft。

下一步建议：
- 跑完整门禁、提交并推送本切片。
- 后续核心切片优先级：simple scalar compound assignment lowering、assignment RHS implicit integral cast preservation、usual conversion 分类。

English mirror summary:

- Added condition-position short-circuit `&&` / `||` candidate generation through generic typed IR.
- `if (left && right)` now emits a Rust bool condition such as `if (left != 0i32 && right != 0i32)`.
- `while ((left < 3) || (right != 0))` emits a Rust bool condition while reusing comparison condition emission.
- Support is intentionally limited to `if` / `while` conditions with C `int` logical result type. Value-position short-circuit, full usual scalar conversions, pointer truthiness, floating-point truthiness, calls/inc/dec/side-effect operands, function pointers, volatile/hardware register semantics, and semantic acceptance still fail closed.

## 103. 2026-06-27 clang-lowered simple scalar compound assignment family

注意：本节是初始 compound-assignment family 切片记录。第 108 节已经在此基础上放开 clang-proven integer promotion/truncation 的窄化路径；恢复时以第 108 节为当前边界。

本轮继续按多智能体并行推进“不要太窄”的核心语法面扩展。只读线程分别复核了 compound assignment、ForStmt 和 ConditionalOperator / `?:`。主线程按 TDD 选择最适合这一轮的宽切片：standalone simple scalar compound assignment family。结论：`+=`、`-=`、`*=`、`/=`、`%=`、`&=`、`|=`、`^=`、`<<=`、`>>=` 现在可以从真实 clang AST 的 `CompoundAssignOperator` 进入 typed IR，并 desugar 成现有 `IrStmt::Assign { value: Binary(...) }`。这不是完整 C compound assignment，也不是 semantic acceptance。

核心改动：
- `crates/c2r-translator/src/clang_frontend.rs`
  - `ClangStmtSkeleton` 新增 `CompoundAssign`；第 108 节已继续补充 result/compute type 字段。
  - `stmt_skeleton_from_ast()` 新增 `CompoundAssignOperator` 分支。
  - 新增 `compound_assignment_operator_from_opcode()`，把 `+=` / `-=` / `*=` / `/=` / `%=` / `&=` / `|=` / `^=` / `<<=` / `>>=` 映射到已有 `ClangBinaryOperator`。
  - 新增 `compound_assignment_type_field()` 和 `compound_assignment_types_match()`。
  - 初始 `compound_assign_stmt_skeleton_from_ast()` 要求：
    - 恰好两个 child；
    - LHS 是 simple `DeclRefExpr`；
    - result/compute 类型边界见第 108 节当前规则。
  - `lower_compound_assign_stmt()` 只把 simple variable target 降成 `x = x op rhs` 的 typed IR；非简单 target fail closed。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 `clang_lowering_skeleton_maps_scalar_compound_assignment_family`，覆盖 10 种 opcode。
  - 新增 `clang_lowering_skeleton_rejects_compound_assignment_non_var_target`，拒绝 `*p += 1` 这类非简单变量 target。
  - 新增 gated real clang smoke `clang_ast_dump_emits_scalar_compound_assignment_family_when_enabled`，实际跑 `value += 1; ... value >>= 1;`。
- `crates/c2r-translator/src/clang_frontend.rs` unit tests
  - 初始切片新增 compute-type 边界测试；第 108 节已把 `unsigned char` / `uint8_t` 的 clang-proven promotion/truncation 改为正测，并保留 unsupported compute 组合负测。
- 双语文档同步：
  - `docs/c2rust-migration-agent/README.md`
  - `docs/c2rust-migration-agent/README.en.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.en.md`

已确认红灯：

```powershell
cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features "typed-ir clang-frontend" compound_assignment -- --nocapture
cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features "typed-ir clang-frontend" stmt_skeleton_from_ast_rejects_compound_assignment_compute_type_mismatch -- --nocapture
```

红灯表现：
- 新 skeleton 测试先编译失败于 `ClangStmtSkeleton::CompoundAssign` 不存在。
- compute type safety test 先失败为错误放行 `unsigned char += int`，生成了 `CompoundAssign`，而不是 `Unsupported`。

已跑过的聚焦绿灯：

```powershell
cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features "typed-ir clang-frontend" stmt_skeleton_from_ast_rejects_compound_assignment_compute_type_mismatch -- --nocapture
cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features "typed-ir clang-frontend" compound_assignment -- --nocapture
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features "typed-ir clang-frontend" compound_assignment -- --nocapture
```

聚焦结果：
- compute type mismatch 单测通过。
- `compound_assignment` filter 6 条通过。
- 真实 clang AST gate 打开后同 6 条实际运行通过，覆盖真实 `CompoundAssignOperator`。

当前边界：
- 可以说：standalone simple scalar variable target 的 10 种 compound assignment 现在可由 clang AST lowering 进入 `GenericTypedIr` candidate。
- 可以说：真实 clang AST 中这些语法是 `CompoundAssignOperator`，不是 `BinaryOperator "+="`。
- 不应说：支持 value-position `(x += y)`、`if (x += y)`、call argument compound assignment、`*p += y`、`a[i] += y`、`s.f += y`、`p->f += y`、未被第 108 节 guard 证明的 promotion/truncation、pointer arithmetic、float、volatile、复杂 RHS side effect、完整 usual conversions 或 semantic acceptance。
- `semantic_pass=false` 仍保持到独立 validation gates 接受 exact draft。

下一步建议：
- 跑完整门禁、提交并推送本切片。
- 后续“更宽语法面”优先级：
  1. assignment RHS implicit integral cast preservation；
  2. pure scalar `ConditionalOperator` / `?:`，但必须新增 `IrExpr::Conditional` 并保护 lazy arm 求值；
  3. `ForStmt`，但最好先引入 block/scope 或明确更窄的作用域 fail-closed 规则，避免 `continue` / init scope 语义偏差。

English mirror summary:

- Added clang-lowered simple scalar compound assignment family support for `+=`, `-=`, `*=`, `/=`, `%=`, `&=`, `|=`, `^=`, `<<=`, and `>>=`.
- Real clang emits these as `CompoundAssignOperator` nodes. The translator now maps them to typed IR assignments of the form `x = x op rhs`.
- This section recorded the initial same-type slice; section 108 supersedes it with a narrow clang-proven integer promotion/truncation path.
- Non-variable targets, value-position compound assignment, unsupported promotion/truncation, pointer arithmetic, floating-point, volatile, side-effect-heavy RHS, full usual conversions, and semantic acceptance still fail closed.

## 104. 2026-06-27 clang-preserved value-position integer implicit casts

本轮继续按多智能体并行推进“尽量拓展语法翻译能力，不要太窄”。只读子智能体分别复核了 value-position implicit cast、ConditionalOperator / `?:` 和 scoped `ForStmt`。结论：`?:` 需要一等 `IrExpr::Conditional` 保护 lazy arms，`ForStmt` 需要 block/scope 模型避免 init scope 和 `continue` 语义偏差；本轮最适合落地的是 clang 已经给出类型证明的 value-position integer implicit casts。

核心结论：declaration initializer、assignment RHS 和 return value 中的 clang `IntegralCast` / `IntegralPromotion` 现在会被保留进 typed IR，随后由现有整数 `IrExpr::Cast` emitter 发射 Rust `as`。这不是 full usual scalar conversions，也不是 semantic acceptance。

核心改动：
- `crates/c2r-translator/src/clang_frontend.rs`
  - 新增 `value_expr_skeleton_from_ast()`，内部调用 `expr_skeleton_from_ast_with_options(expr, true)`。
  - `DeclStmt` initializer、assignment RHS 和 `ReturnStmt` value 改为走 `value_expr_skeleton_from_ast()`。
  - target expression、condition expression、普通 expression statement 仍不因此放开新语义。
  - 未新增 typed IR 结构；复用已有 `ClangExprSkeleton::Cast` / `IrExpr::Cast`。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增真实 clang smoke：
    - `clang_ast_dump_emits_unsigned_assignment_rhs_integral_cast_when_enabled`
    - `clang_ast_dump_emits_unsigned_decl_and_return_integral_casts_when_enabled`
- `crates/c2r-translator/src/clang_frontend.rs` unit tests
  - 新增：
    - `stmt_skeleton_from_ast_preserves_assignment_rhs_integral_cast`
    - `stmt_skeleton_from_ast_preserves_decl_initializer_integral_cast`
    - `stmt_skeleton_from_ast_preserves_return_value_integral_cast`
- 双语文档同步：
  - `docs/c2rust-migration-agent/README.md`
  - `docs/c2rust-migration-agent/README.en.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.en.md`

已确认红灯：

```powershell
cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features "typed-ir clang-frontend" preserves_ -- --nocapture
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features "typed-ir clang-frontend" unsigned_ -- --nocapture
```

红灯表现：
- assignment RHS / decl initializer / return value 的 `IntegralCast` 被剥掉，IR 里只剩 `LitInt { ty: int }`。
- 真实 clang 用例 `uint32_t value = 1; value = 2; return 3;` 不能生成期望的 `(1i32 as u32)` / `(2i32 as u32)` / `(3i32 as u32)`。

已跑过的聚焦绿灯：

```powershell
cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features "typed-ir clang-frontend" preserves_ -- --nocapture
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features "typed-ir clang-frontend" unsigned_ -- --nocapture
```

聚焦结果：
- `preserves_` filter 8 条通过。
- 真实 clang gate 打开后 `unsigned_` filter 4 条通过，其中新增 2 条实际运行并通过。

当前边界：
- 可以说：clang AST 中 declaration initializer、assignment RHS、return value 的 `IntegralCast` / `IntegralPromotion` 现在能进入 `GenericTypedIr` candidate，并由 Rust `as` 发射。
- 可以说：例如 `uint32_t set_unsigned_one(uint32_t value) { value = 1; return value; }` 现在能发射 `value = (1i32 as u32);`。
- 不应说：支持完整 usual scalar conversions、函数指针 decay、pointer cast、float cast、隐藏副作用转换、所有 mixed-width 算术、语义等价接受或 validation semantic pass。
- typed IR emitter 仍会要求 source/target 是受支持整数类型，且 statement boundary 类型最终匹配。

下一步建议：
- 跑完整门禁、提交并推送本切片。
- 后续更大语法切片优先级：
  1. pure scalar `ConditionalOperator` / `?:`，但必须新增 `IrExpr::Conditional` 并保护 lazy arms；
  2. scoped `ForStmt`，但应先引入 block/scope 或明确更窄的 fail-closed 规则，避免 init scope / `continue` 语义偏差；
  3. 更系统的 usual conversion 分类，而不是把所有 `ImplicitCastExpr` 直接放行。

English mirror summary:

- Added clang-preserved value-position integer implicit cast preservation for declaration initializers, assignment RHS, and return values.
- The implementation reuses existing `ClangExprSkeleton::Cast` / `IrExpr::Cast`; no new IR structure was added.
- Real clang cases such as `uint32_t value = 1; value = 2; return 3;` now emit Rust integer casts such as `(1i32 as u32)`.
- This is candidate generation only. Full usual scalar conversions, function-pointer decay, pointer casts, floating-point casts, hidden side-effect conversions, semantic acceptance, and validation `semantic_pass` still fail closed.

## 105. 2026-06-27 pure integer value-position ConditionalOperator / ?:

本轮继续按多智能体并行推进核心语法面扩展。只读子智能体分别复核了 typed IR `Conditional` 递归点、clang AST `ConditionalOperator` / `BinaryConditionalOperator` 形态，以及 fail-closed 文档边界；主线程按 TDD 落地最小安全切片：只支持纯整数 value-position `?:`，覆盖 return value、assignment RHS 和 declaration initializer。结论：普通 clang `ConditionalOperator` 现在可以 lowering 到一等 lazy `IrExpr::Conditional`，并由 generic typed IR emitter 发射 Rust `if cond { then } else { else }` 表达式；这不是完整 C `?:`，也不是 semantic acceptance。

核心改动：
- `crates/c2r-translator/src/typed_ir.rs`
  - `IrExpr` 新增 `Conditional { condition, then_expr, else_expr, ty }`。
  - `emit_expr()` / `emit_expr_with_prelude()` 新增 conditional value-position 发射，condition 复用 `emit_condition_expr()`，then/else 直接用 `emit_expr()`，不把分支 prelude 提前到 `if` 外。
  - 新增 fail-closed guard：then/else 分支含 call、inc/dec、post-increment byte read、assignment/comma 或类型不匹配时拒绝。
  - `emit_condition_expr()` 显式拒绝 condition-position conditional；`validate_bounded_call_arg()` 和 `validate_readonly_pointer_add_index_expr()` 也继续拒绝 conditional。
  - 所有需要递归扫描 `IrExpr` 的 call evidence、post-increment、nullable pointer 和类型 helper 已覆盖 `condition/then_expr/else_expr`。
- `crates/c2r-translator/src/clang_frontend.rs`
  - `ClangExprSkeleton` 新增 `Conditional`。
  - `expr_skeleton_from_ast_with_options()` 支持普通 `ConditionalOperator`，then/else 分支强制保留 value-position integer casts。
  - `BinaryConditionalOperator` / GNU `a ?: b` 显式转成 unsupported，避免破坏 lhs 单求值语义。
  - `lower_expr()` 把 skeleton lowering 成 `IrExpr::Conditional`。
- `crates/c2r-translator/src/lib.rs`
  - clang lowering report 的 call evidence、source text、label 和 post-increment scan 已支持 `Conditional`。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 direct typed IR 正测：return value、assignment RHS、declaration initializer。
  - 新增 direct typed IR 负测：arm 类型不匹配、arm call、arm post-increment byte read、arm assignment、condition-position conditional。
  - 新增 clang skeleton 正测和真实 clang AST smoke：return value、assignment RHS、declaration initializer、unsigned branch integral cast。
  - 新增真实 clang AST fail-closed：GNU `value ?: fallback` / `BinaryConditionalOperator`。
- 双语文档同步：
  - `docs/c2rust-migration-agent/README.md`
  - `docs/c2rust-migration-agent/README.en.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.en.md`
  - `codex/translator-strengthening-analysis.md`
  - `codex/translator-strengthening-analysis.en.md`

已跑过的聚焦绿灯：
```powershell
cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir conditional_ -- --nocapture
$env:C2R_RUN_CLANG_AST_TESTS='1'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir conditional_ -- --nocapture
```

聚焦结果：
- `conditional_` filter 在 `clang-frontend,typed-ir` 下 14 条通过。
- 打开真实 clang AST gate 后同 14 条实际运行并通过，覆盖普通 `ConditionalOperator` 与 GNU `BinaryConditionalOperator` 拒绝。

当前边界：
- 可以说：纯整数 value-position `?:` 现在能从真实 clang AST 进入 `GenericTypedIr`，生成可编译 Rust candidate。
- 可以说：`uint32_t choose(uint32_t flag, uint32_t value) { return flag ? value : 2; }` 会保留 else arm 的 clang integral cast 并发射 `(2i32 as u32)`。
- 不应说：已支持 condition-position `?:`、expression-statement `?:`、GNU `a ?: b`、pointer/float/aggregate result、arm 内 call/inc/dec/post-increment/assignment/comma 副作用、完整 usual scalar conversions 或 semantic acceptance。
- `semantic_pass=false` 仍保持到独立 validation gates 接受 exact draft。

下一步建议：
- 跑完整门禁、提交并推送本切片。
- 后续核心语法优先级：scoped `ForStmt`、value-position short-circuit materialization、usual conversion 分类、struct/field/memory model 设计。

English mirror summary:

- Added pure integer value-position `ConditionalOperator` / `?:` candidate generation.
- Ordinary clang `ConditionalOperator` lowers to first-class lazy `IrExpr::Conditional` and emits Rust `if cond { then } else { else }` expressions.
- Return values, assignment RHS, declaration initializers, and clang-preserved integer casts in branches are covered by direct, skeleton, and real clang smoke tests.
- GNU omitted-middle `a ?: b`, condition-position `?:`, expression-statement `?:`, side-effecting branches, pointer/float/aggregate results, full usual conversions, and semantic acceptance still fail closed.

## 106. 2026-06-27 value-position short-circuit through typed IR

本轮继续按多智能体并行推进“尽量拓展语法翻译能力，不要太窄”。只读子智能体分别复核了 value-position `&&` / `||` 的 lazy materialization 方案、scoped `ForStmt` 风险，以及 usual conversion 边界；主线程按 TDD 落地最小安全切片：支持 C short-circuit `&&` / `||` 在 value-position 中生成 C `int` 0/1 candidate，覆盖 return value、assignment RHS 和 declaration initializer。结论：这是通用 typed IR candidate generation 能力，不是 FlashDB 专用代码，也不是 semantic acceptance。

核心改动：
- `crates/c2r-translator/src/typed_ir.rs`
  - 新增 `emit_short_circuit_value_expr()`，复用现有 `emit_short_circuit_condition_expr()` / `emit_condition_expr()` 生成 Rust bool condition。
  - value-position 发射为 `(if <condition> { 1i32 } else { 0i32 })`，其中 `<condition>` 仍使用 Rust `&&` / `||`，保留 RHS lazy 求值。
  - `emit_expr()` 和 `emit_expr_with_prelude()` 都在普通 binary op fallback 之前识别 `IrBinOp::LogAnd` / `IrBinOp::LogOr`。
  - 结果类型仍必须是 C `int`；operand 子集继续继承当前 condition emitter：整数 truthiness、comparison、logical-not、readonly deref 和 bounded offset-deref read。call/inc/dec/side-effect operand、pointer truthiness、float truthiness、unsupported type 和未建模 usual conversions 继续 fail closed。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 删除旧的“value-position short-circuit 必须拒绝”负测，改为 direct typed IR 正测：
    - `typed_ir_emits_short_circuit_return_value_as_c_int`
    - `typed_ir_emits_short_circuit_assignment_value_as_c_int`
    - `typed_ir_emits_short_circuit_decl_initializer_as_c_int`
  - 新增 fail-closed：
    - `typed_ir_rejects_short_circuit_value_with_non_int_result_type`
    - `typed_ir_rejects_short_circuit_value_with_call_operand`
  - 新增 clang skeleton 正测 `clang_lowering_skeleton_maps_short_circuit_value_positions`。
  - 新增真实 clang AST smoke `clang_ast_dump_emits_short_circuit_value_positions_when_enabled`，覆盖 `int out = left || right; left = left && (right > 0); return left || out;`。
- 双语文档同步：
  - `docs/c2rust-migration-agent/README.md`
  - `docs/c2rust-migration-agent/README.en.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.en.md`
  - `codex/translator-strengthening-analysis.md`
  - `codex/translator-strengthening-analysis.en.md`

红灯已确认：
```powershell
cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir short_circuit -- --nocapture
```

红灯表现：
- 新增 value-position 正测失败于 `binary op LogAnd is unsupported` / `binary op LogOr is unsupported`。
- non-C-int result 和 call operand 负测也先失败为普通 unsupported，而不是专门的 short-circuit 边界错误。

已跑过的绿灯：
```powershell
cargo fmt --manifest-path .\crates\c2r-translator\Cargo.toml -- --check
git diff --check
$env:C2R_RUN_CLANG_AST_TESTS='1'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir short_circuit -- --nocapture
$env:C2R_RUN_CLANG_AST_TESTS='1'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir,clang-lowering-report -- --nocapture
```

聚焦与完整结果：
- `short_circuit` filter 在真实 clang gate 打开后 12 条通过。
- 完整 `clang-frontend,typed-ir,clang-lowering-report` 回归通过：lib 37 条、`bounded_translation` 301 条、doc-tests 0 条。

当前边界：
- 可以说：condition-position 和窄 value-position `&&` / `||` 现在能从 direct typed IR、clang skeleton 和真实 clang AST 进入 `GenericTypedIr`，并生成可编译 Rust candidate。
- 可以说：`return left && right`、`out = left || right`、`int out = left && (right > 0)` 现在会发射 C `int` 0/1 materialization，并保留 Rust short-circuit lazy 求值。
- 不应说：已支持 pointer truthiness、float truthiness、call/inc/dec/side-effect operand、完整 usual scalar conversions、函数指针、volatile/hardware register、跨线程/中断语义或 semantic acceptance。
- 旧第 102 节“只支持 condition-position short-circuit”和第 105 节“下一步 value-position short-circuit materialization”的说法已被本节 supersede；后续按本节读取最新状态。

下一步建议：
- 下一个核心语法切片优先 scoped `ForStmt`，但必须引入一等 `IrStmt::For` 或 scoped block，不能裸降成同级 `Decl + While`，否则会破坏 init scope 和 `continue` 语义。
- usual conversions 继续只做 clang/type-map 已证明的整数 cast/promotion 子集，不要一次性放开完整 C conversion。

English mirror summary:

- Added narrow value-position short-circuit `&&` / `||` candidate generation through generic typed IR.
- `return left && right`, assignment RHS, and declaration initializers now materialize C `int` 0/1 as Rust `if condition { 1i32 } else { 0i32 }`.
- The condition still uses Rust `&&` / `||`, preserving lazy RHS evaluation.
- Direct typed IR, clang skeleton, and real clang AST smoke tests cover the new path.
- Pointer truthiness, floating-point truthiness, calls/inc/dec/side-effect operands, full usual scalar conversions, function pointers, volatile/hardware register semantics, cross-thread/interrupt semantics, and semantic acceptance still fail closed.

## 107. 2026-06-27 scoped typed IR ForStmt lowering

本轮继续按多智能体并行推进“尽量拓展语法翻译能力，不要太窄”。两个只读子智能体分别复核了 typed IR `ForStmt` scope 模型和 clang `ForStmt` AST 槽位/文档同步；主线程按 TDD 落地 scoped `ForStmt` MVP。结论：这是通用 typed IR candidate generation 能力，不是 FlashDB 专用代码，也不是 semantic acceptance。第 106 节“下一刀优先 scoped `ForStmt`”已被本节 supersede；后续优先 usual conversions 分类，或在已有 scoped MVP 上继续设计 `break` / `continue` / `do-while` / `switch` / `goto`。

核心改动：
- `crates/c2r-translator/src/typed_ir.rs`
  - 新增一等 `IrStmt::For { init, condition, step, body }`。
  - 新增 scoped emitter：发射为外层 Rust block + `while`，例如 `for (int i = 0; i < limit; i++)` 生成 `{ let mut i: i32 = 0i32; while i < limit { ...; i = i + 1i32; } }`。
  - loop-init 声明只写入 loop block scope，不回写父级；body 局部声明不会泄漏到 step。
  - `validate_for_init_stmt()` 只接受 `Decl` / `Assign`；`validate_for_step_stmt()` 只接受 `Assign`。
  - nullable pointer、byte cursor、post-increment scan、assigned-var scan 等递归 helper 已覆盖 `For`。
- `crates/c2r-translator/src/clang_frontend.rs`
  - 新增 `ClangStmtSkeleton::For` 和 `for_stmt_skeleton_from_ast()`。
  - clang `ForStmt.inner` 按 5 槽位解析：init、condition variable slot、condition、step、body。
  - condition variable slot、空 condition、空 step 均 fail closed。
  - init 只接受简单 `DeclStmt` 或 assignment；step 只接受 assignment、compound assignment 和 postfix inc/dec；postfix `i++` / `i--` lowering 成 `i = i + 1` / `i = i - 1`。
  - `continue` / `break` / `goto` / `switch` 等未建模 body statement 继续通过 unsupported skeleton fail closed。
- `crates/c2r-translator/src/lib.rs`
  - 修复 `clang-lowering-report` feature 下的 report/evidence 遍历：type mapping、direct call evidence、statement kind、CFG edge、byte cursor pointer scan 都已识别或递归 `IrStmt::For`。
  - 新增单元测试覆盖 `For` statement kind、`entry->for-*` CFG edge、loop init/body type map 和 body/step direct call evidence。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 direct typed IR 正测：scoped loop emit + rustc smoke。
  - 新增 direct typed IR 负测：init decl 不泄漏到父级、body decl 不泄漏到 step、decl step 拒绝、非 C `int` condition result 拒绝。
  - 新增 clang skeleton 正测和真实 clang AST smoke：`int sum_to_limit(int limit) { int total = 0; for (int i = 0; i < limit; i++) { total = total + i; } return total; }`。
  - 新增真实 clang fail-closed：`continue` in for body、缺 condition、缺 step、prefix `++i` step。
- 双语文档同步：
  - `docs/c2rust-migration-agent/README.md`
  - `docs/c2rust-migration-agent/README.en.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.en.md`
  - `codex/translator-strengthening-analysis.md`
  - `codex/translator-strengthening-analysis.en.md`
  - `docs/superpowers/plans/2026-06-27-typed-ir-scoped-forstmt.md`

红灯已确认：
```powershell
$env:C2R_RUN_CLANG_AST_TESTS='1'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir typed_ir_for -- --nocapture
```

红灯表现：
- 新增 direct typed IR 测试在 `IrStmt::For` 不存在时编译失败。
- 新增 clang skeleton/real clang 测试在 `ClangStmtSkeleton::For` 不存在时编译失败。

调试中额外发现并修复：
- 完整 `clang-frontend,typed-ir,clang-lowering-report` feature 组合最初失败于 `src/lib.rs` 的多个 `match IrStmt` 未覆盖 `For`。
- 根因是 `clang-lowering-report` 的 evidence/report helper 在前一轮未随新 statement variant 同步递归。
- 修复后新增 `clang_lowered_ir_evidence_tests::clang_lowered_ir_records_for_statement_evidence_recursively` 锁住该路径。

已跑过的绿灯：
```powershell
$env:C2R_RUN_CLANG_AST_TESTS='1'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir typed_ir_for -- --nocapture
$env:C2R_RUN_CLANG_AST_TESTS='1'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir,clang-lowering-report -- --nocapture
```

聚焦与完整结果：
- `typed_ir_for` filter 在真实 clang gate 打开后 12 条通过。
- 完整 `clang-frontend,typed-ir,clang-lowering-report` 回归通过：lib 38 条、`bounded_translation` 312 条、doc-tests 0 条。

当前边界：
- 可以说：窄化 scoped `ForStmt` 现在能从 direct typed IR、clang skeleton 和真实 clang AST 进入 `GenericTypedIr`，并生成可编译 Rust candidate。
- 可以说：simple scalar init/condition/assignment step、compound assignment step、postfix inc/dec step 和现有 statement body 子集已有测试覆盖。
- 不应说：已支持 `continue` / `break` / `goto` / `switch`、condition variable slot、空 condition/step、prefix inc/dec step、复杂 init/step、完整 C for-loop control-flow semantics、完整 usual scalar conversions 或 semantic acceptance。

下一步建议：
- 优先 usual conversions 分类：把 clang 已证明的 integral cast/promotion 继续系统化，而不是一次性放开完整 C conversion。
- 或继续控制流：在已有 scoped `ForStmt` MVP 上，单独设计 `break` / `continue` 的 step 语义、CFG evidence 和 validation gate。

English mirror summary:

- Added narrow scoped `ForStmt` candidate generation through generic typed IR.
- `IrStmt::For` emits a Rust block plus `while`, keeping loop-init declarations scoped to the loop block and preventing body-local declarations from leaking into the step.
- Clang `ForStmt` lowering accepts simple scalar init, required condition, required assignment/compound-assignment/postfix-inc-dec step, and the existing body subset.
- Direct typed IR, clang skeleton, and real clang AST smoke tests cover the new path, including fail-closed real-clang tests for `continue`, missing condition, missing step, and prefix increment step.
- The `clang-lowering-report` feature now traverses `For` for type mapping, call evidence, statement kinds, CFG edges, and byte-cursor pointer scans.
- `continue`, `break`, `goto`, `switch`, condition variable slots, empty condition/step, prefix inc/dec steps, complex init/step, full C for-loop control-flow semantics, full usual scalar conversions, and semantic acceptance still fail closed.

## 108. 2026-06-27 clang-proven compound assignment integer promotion

本轮继续拓展 `c2r-translator` 核心 typed IR 翻译能力，不写 FlashDB 专用分支。切片目标是把 clang 已证明的 `CompoundAssignOperator` 整数提升/回写截断打通，例如：

```c
#include <stdint.h>
uint8_t compound_assignment_integer_promotion(uint8_t value) {
    value += 1;
    return value;
}
```

现在能 lower 成 typed IR：

```rust
value = (((value as i32) + 1i32) as u8);
```

核心改动：
- `crates/c2r-translator/src/clang_frontend.rs`
  - `ClangStmtSkeleton::CompoundAssign` 新增 `result_ty`、`compute_lhs_ty`、`compute_result_ty`。
  - `compound_assign_stmt_skeleton_from_ast()` 不再要求 compute type 必须等于 target type；改为要求 target/result 一致、compute lhs/result 一致、且 target/compute 都是受支持整数。
  - `lower_compound_assign_stmt()` 对 lhs/rhs 显式 cast 到 compute type，再把 binary 结果 cast 回 target type。
  - `ir_types_match_for_clang()` / `cast_ir_expr_to_type_if_needed()` 避免 clang spelling 差异导致误拒或多余判断。
  - simple `ForStmt` compound-assignment step 通过现有 step parser 继承同一个 guard。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 direct typed IR 测试：`typed_ir_emits_scalar_assignment_with_integer_promotion_and_truncation`。
  - 新增 clang skeleton 测试：`clang_lowering_skeleton_maps_compound_assignment_integer_promotion`。
  - 新增真实 clang smoke：`clang_ast_dump_emits_compound_assignment_integer_promotion_when_enabled`。
  - 原 `compound_assignment` family、non-var target、ForStmt step、bounded translator 记录规则回归仍通过。
- 双语/设计文档同步：
  - `docs/c2rust-migration-agent/README.md`
  - `docs/c2rust-migration-agent/README.en.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.en.md`
  - `codex/translator-strengthening-analysis.md`
  - `codex/translator-strengthening-analysis.en.md`
  - `docs/superpowers/specs/2026-06-27-candidate-route-p0-design.md`
  - `docs/superpowers/specs/2026-06-27-candidate-route-p0-design.en.md`
  - `docs/superpowers/plans/2026-06-27-compound-assignment-integer-promotion.md`
  - `docs/superpowers/plans/2026-06-27-typed-ir-scoped-forstmt.md`
  - `openspec/changes/expand-translator-compound-statement-support/*`

聚焦验证已通过：

```powershell
$env:C2R_RUN_CLANG_AST_TESTS='1'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir integer_promotion -- --nocapture
$env:C2R_RUN_CLANG_AST_TESTS='1'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir compound_assignment -- --nocapture
```

边界：
- 可以说：standalone statement 和 simple `ForStmt` step 中的 simple scalar compound assignment，现在支持 clang-proven integer promotion/truncation。
- 可以说：`uint8_t value; value += 1;` 会用 compute `int` 做加法，再显式 cast 回 `u8`。
- 不应说：已支持完整 usual scalar conversions、非简单 lvalue target、value-position `(x += y)`、pointer arithmetic、float、volatile、复杂 RHS side effect、semantic acceptance。

下一步建议：
- 继续做 usual conversions 分类，但仍按 clang/type-map 已证明的小切片推进；不要一次性打开完整 C conversion。
- 可以选的后续切片：comparison/binary operand 的更系统 mixed-width guard，或者在 scoped `ForStmt` 上设计 `break` / `continue` 的 step 语义和 evidence。

English mirror summary:

- Added narrow clang-proven compound-assignment integer promotion/truncation candidate generation.
- `ClangStmtSkeleton::CompoundAssign` now carries result and compute types.
- Lowering accepts target/result match plus compute-lhs/compute-result match when all involved types are supported integers, even if compute type differs from target type.
- `uint8_t value; value += 1;` now emits `value = (((value as i32) + 1i32) as u8);`.
- Direct typed IR, clang skeleton, real clang AST smoke, and compound-assignment regression filters pass.
- Full usual scalar conversions, non-simple targets, value-position compound assignment, pointer arithmetic, floating-point, volatile, complex RHS side effects, and semantic acceptance still fail closed.

## 109. 2026-06-27 fixed-width integer type coverage

本轮继续拓展 `c2r-translator` 核心 clang-lowered typed IR 翻译能力，不写 FlashDB 专用分支。切片目标是把真实 clang AST 中的固定宽度整数 typedef aliases 接到现有 typed IR 整数类型和 generic emitter 上。结论：当前 fixed-width alias 全集 `int8_t`、`int16_t`、`int32_t`、`int64_t`、`uint8_t`、`uint16_t`、`uint32_t`、`uint64_t` 能进入 typed IR 并生成可编译 Rust；本轮新增的是 signed aliases 和 `uint16_t` / `uint64_t`。这不是完整 usual scalar conversions，也不是 raw C integer spelling 或 target ABI 类型推断，更不是 semantic acceptance。

核心改动：
- `crates/c2r-translator/src/clang_frontend.rs`
  - `type_from_qual_type()` 新增固定宽度整数标量映射：
    - `int8_t` -> signed 8-bit canonical `int8_t`。
    - `int16_t` -> signed 16-bit canonical `int16_t`。
    - `int32_t` -> signed 32-bit canonical `int32_t`，plain `int` 映射保持不变。
    - `int64_t` -> signed 64-bit canonical `int64_t`。
    - `uint16_t` -> unsigned 16-bit canonical `uint16_t`。
    - `uint64_t` -> unsigned 64-bit canonical `uint64_t`。
  - raw `signed char`、`short`、`unsigned short`、`long long`、`unsigned long long` 保持 unsupported；plain `char` 和 plain `long` 仍未放开；既有 `unsigned char` / `unsigned int` / `unsigned long` 行为保持原样，避免把本轮变成 target ABI integer model 重构。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增真实 clang smoke：`clang_ast_dump_emits_fixed_width_integer_types_when_enabled`。
  - smoke source 使用 `<stdint.h>` identity 函数覆盖 `int8_t` / `int16_t` / `int32_t` / `uint16_t` / `int64_t` / `uint64_t`，并逐个经过 clang AST lowering、`emit_rust_from_ir()` 和 rustc snippet 编译。
  - 新增负测：`type_from_qual_type_keeps_target_dependent_integer_spellings_unsupported`，证明 raw target-dependent spelling 没有被这轮放开。
- 双语/设计文档同步：
  - `docs/c2rust-migration-agent/README.md`
  - `docs/c2rust-migration-agent/README.en.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.en.md`
  - `codex/translator-strengthening-analysis.md`
  - `codex/translator-strengthening-analysis.en.md`
  - `docs/superpowers/plans/2026-06-27-fixed-width-integer-type-coverage.md`

红灯已观察：

```powershell
$env:C2R_RUN_CLANG_AST_TESTS='1'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir fixed_width_integer -- --nocapture
```

旧代码在 `type_from_qual_type_maps_fixed_width_integer_scalars` 中失败，因为 `int8_t` / `int16_t` / `uint16_t` / `int64_t` / `uint64_t` 等 fixed-width aliases 仍不能全部映射到目标 typed IR 整数类型。审查后新增的 raw spelling 负测先失败于当前实现错误放行 `signed char` / `short` / `long long` 等 target-dependent spelling。

聚焦验证已通过：

```powershell
$env:C2R_RUN_CLANG_AST_TESTS='1'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir fixed_width_integer -- --nocapture
```

边界：
- 可以说：固定宽度整数 typedef aliases 现在可进入 typed IR，并发射 Rust `i8` / `i16` / `i32` / `i64` / `u8` / `u16` / `u32` / `u64`。
- 不应说：已支持 raw `signed char` / `short` / `long long` 这类 target-dependent spelling、plain `char`、plain `long`、target-dependent ABI 宽度推断、完整 integer promotion/usual scalar conversions、跨目标 C integer model 或 semantic acceptance。

下一步建议：
- 优先做多 `VarDecl` declaration statement expansion，例如 `int a = 1, b = 2;`，这是 clang skeleton 常见形态，和 fixed-width 类型覆盖互补且写入面清晰。
- 另一个方向是继续 usual conversions 分类，但仍按 clang/type-map 已证明的小切片推进。

English mirror summary:

- Added fixed-width integer typedef alias coverage in the clang frontend type skeleton.
- The current fixed-width alias set `int8_t`, `int16_t`, `int32_t`, `int64_t`, `uint8_t`, `uint16_t`, `uint32_t`, and `uint64_t` lowers through typed IR and emits Rust `i8`, `i16`, `i32`, `i64`, `u8`, `u16`, `u32`, and `u64`; this slice newly adds the signed aliases plus `uint16_t` / `uint64_t`.
- Raw target-dependent spellings such as `signed char`, `short`, `long long`, `unsigned short`, and `unsigned long long` are not normalized to fixed-width canonical types in this slice.
- Plain `char`, plain `long`, target-ABI width inference, complete usual scalar conversions, and semantic acceptance still fail closed.
- Direct type unit coverage and real clang AST smoke coverage pass for this slice.
