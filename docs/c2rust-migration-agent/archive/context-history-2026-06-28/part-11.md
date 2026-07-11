## 136. 2026-06-28 P0 write_translation_artifacts orchestration split

本轮继续按 P0 拆分 `crates/c2r-translator/src/lib.rs`，把 `write_translation_artifacts()` public orchestration 移入 `artifacts.rs`。这仍然是行为保持重构：不新增 C 语法翻译能力，不改变 crate root public API，不改变 artifact 文件名、artifact 顺序、manifest status、feature gate、Python opt-in 或 semantic pass claim。

核心改动：
- `crates/c2r-translator/src/artifacts.rs`
  - 新增 `pub fn write_translation_artifacts(...)`，负责建目录、选择默认/clang-lowered translation result、写 8 个核心 artifacts、追加 optional clang dry-run / lowering-report artifacts，并返回 `ArtifactManifest`。
  - 同步迁入私有 helper `translate_slice_with_optional_clang_lowered_ir()`；它只服务 `clang-lowering-report` feature 下的 artifact orchestration。
  - 新增模块边界测试 `core_translation_artifact_tests::write_translation_artifacts_public_orchestration_stays_in_artifacts_module`。
- `crates/c2r-translator/src/lib.rs`
  - 改为 `pub use artifacts::write_translation_artifacts;`，继续保持 `c2r_translator::write_translation_artifacts` 外部路径兼容。
  - 当前约 69 行，只保留 module declarations、public re-export 和两个模块边界测试。
- 同步中英文 MVP 待办：
  - `docs/c2rust-migration-agent/future-vision-and-mvp.md`
  - `docs/c2rust-migration-agent/future-vision-and-mvp.en.md`
  - 将 `lib.rs` 当前规模更新为约 69 行，并把 `write_translation_artifacts` public orchestration 拆分列为已完成子项；P0 总项仍保持未完成。

TDD 证据：
- 红测先失败于 `cannot find function write_translation_artifacts in this scope`，证明 orchestration 尚未在 `artifacts.rs` 模块内。
- 迁移后同一测试通过，并确认默认 feature 下仍只写 8 个核心 artifact。
- 后续 feature matrix 暴露测试断言过窄：`clang-frontend` 会追加 dry-run artifact，`clang-lowering-report` 会追加 dry-run + lowering-report artifact；测试已改为按 feature 期待 8/9/10 个 artifact，并显式检查 optional artifact 文件存在。

当前已验证：

```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml write_translation_artifacts_public_orchestration_stays_in_artifacts_module
cargo fmt --manifest-path crates/c2r-translator/Cargo.toml -- --check
cargo check --manifest-path crates/c2r-translator/Cargo.toml --all-targets --all-features
cargo test --manifest-path crates/c2r-translator/Cargo.toml --quiet
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-frontend --quiet
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir --quiet
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features "typed-ir clang-frontend" --quiet
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report --quiet
cargo test --manifest-path crates/c2r-translator/Cargo.toml --all-features --quiet
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_route_baseline_and_validation_profile_evidence_are_emitted validation.tools.test_auto_migrate.AutoMigrateTests.test_run_translator_default_does_not_enable_clang_features validation.tools.test_auto_migrate.AutoMigrateTests.test_cache_identity_keeps_clang_lowering_report_fields_out_by_default validation.tools.test_auto_migrate.AutoMigrateTests.test_run_translator_emit_clang_lowering_report_enables_report_feature validation.tools.test_auto_migrate.AutoMigrateTests.test_cache_identity_records_emit_clang_lowering_report_opt_in validation.tools.test_auto_migrate.AutoMigrateTests.test_run_translator_emit_clang_dry_run_does_not_enable_lowering_report_feature
git diff --check
```

结果：
- artifact orchestration 模块边界红绿测试通过。
- `cargo fmt --check`：exit 0。
- `cargo check --all-targets --all-features`：exit 0。
- 默认 feature：4 个 lib tests + 35 个 bounded tests + doc tests 通过。
- `clang-frontend`：5 个 lib tests + 44 个 bounded tests + doc tests 通过。
- `typed-ir`：4 个 lib tests + 220 个 bounded tests + doc tests 通过。
- `typed-ir clang-frontend`：53 个 lib tests + 395 个 bounded tests + doc tests 通过。
- `clang-lowering-report`：63 个 lib tests + 396 个 bounded tests + doc tests 通过。
- `--all-features --quiet`：63 个 lib tests + 396 个 bounded tests + doc tests 通过。
- Python 默认/clang optional route/profile/cache opt-in 定向测试：6/6 passed。
- `git diff --check`：exit 0，仅 Windows LF-to-CRLF warnings。

边界：
- 可以说：`write_translation_artifacts()` public orchestration 已从 `lib.rs` 拆到 `artifacts.rs`，crate root public API 保持兼容。
- 可以说：`lib.rs` 现在基本只剩 crate root module/re-export surface。
- 不应说：P0 全部完成、CLI/manifest orchestration 已完全模块化、generic typed IR route 已拆完、新增任何 C 语法翻译能力、或任何 candidate 因本次拆分获得 semantic pass。

English mirror summary:

- Moved `write_translation_artifacts` public orchestration into `artifacts.rs`.
- Kept the crate-root public API compatible through `pub use artifacts::write_translation_artifacts`.
- Preserved default artifacts, optional clang artifacts, manifest status behavior, feature gates, Python opt-in behavior, and semantic claim boundaries.
- Added a module-boundary red/green test proving the orchestration now lives in the artifacts module.
- Updated the Chinese and English MVP backlog to mark this sub-split done while keeping the broader P0 split open.

## 137. 2026-06-28 P1 readonly record pointer arrow field read

本轮继续按多智能体推进 P1 record/pointer 子集，不写 FlashDB/crc32 特例。三个只读代理共同审查了 typed IR emitter、clang lowering 和当前 diff；结论是：`const struct T *p` 的简单 `p->scalar_field` 可以作为窄的 readonly single-object candidate 进入 generic typed IR，但它必须映射为 `&T` 而不是 slice，并且不能顺手放开 pointer field writes、compound/update writes、nullable pointer、pointer arithmetic 或 alias-sensitive ownership 语义。

核心改动：
- `crates/c2r-translator/src/typed_ir.rs`
  - `emit_param_type()` 现在把 readonly record pointer pointee（`Pointer` to `const Record`）映射为 `&RecordName`，与 readonly integer pointer 的 `&[T]` slice 路径分开。
  - `emit_member_expr()` 对 `is_arrow=true` 增加窄路径 `emit_readonly_record_pointer_member_expr()`：base 必须是已声明变量，类型必须是 readonly record pointer，字段结果必须是 scalar，最终发射 `p.x`。
  - `emit_assignment_target()` 对 `is_arrow=true` 的 member target 显式 fail closed，错误为缺少 pointer/record ownership evidence；所以 `p->x = value` 和 compound write shape 不会因为 read 路径放开而通过。
  - `emit_record_definitions()` 会从 readonly record pointer pointee 和字段访问合并 record field inventory。
  - `add_record_field_use()` 允许同一整数字段声明类型与 const record 读取表达式类型之间仅有顶层 const 差异，例如 `int` 与 `const int`，但仍拒绝真正不同的 field 类型。
- `crates/c2r-translator/src/clang_frontend.rs`
  - `attach_record_inventory_to_function()` 现在处理函数参数。
  - `attach_record_inventory_to_type()` 递归进入 pointer pointee 和 array element，使真实 clang AST 中 `const struct point *p` 的 pointee 能拿到完整 `RecordDecl`/`FieldDecl` 清单。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - `typed_ir_emits_readonly_record_pointer_arrow_field_read`：手写 typed IR 正例，生成 `pub fn point_x(p: &Point) -> i32` 和 `return p.x;`。
  - `typed_ir_rejects_record_arrow_field_assignment`：readonly record pointer 的 `p->x = value` 仍拒绝。
  - `typed_ir_rejects_record_arrow_field_compound_assignment_shape`：`p->x += value` 的 typed IR compound shape 仍拒绝。
  - `typed_ir_rejects_mutable_record_pointer_arrow_field_read`：非 const `struct point *` 的 arrow read 仍拒绝。
  - `clang_ast_dump_emits_readonly_record_pointer_arrow_member_read_when_enabled`：真实 clang AST smoke 断言 IR shape 是 `Return(Member { is_arrow: true, base: Var("p"), field: "x" })`，并验证 Rust candidate 包含完整字段 `x` 和 `y`，再通过 rustc snippet smoke。
- `docs/c2rust-migration-agent/future-vision-and-mvp.md` 和 `.en.md`
  - 同步标注 readonly `const struct T *p` 的简单 `p->scalar_field` 读已进入 typed IR candidate 子集，同时明确 pointer field writes 仍拒绝。

已验证：

```powershell
cargo fmt --manifest-path crates/c2r-translator/Cargo.toml -- --check
cargo check --manifest-path crates/c2r-translator/Cargo.toml --all-targets --all-features
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir --quiet
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features "typed-ir clang-frontend" --quiet
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report --quiet
cargo test --manifest-path crates/c2r-translator/Cargo.toml --all-features --quiet
cargo test --manifest-path crates/c2r-translator/Cargo.toml --quiet
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-frontend --quiet
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --manifest-path crates/c2r-translator/Cargo.toml --features "typed-ir clang-frontend" clang_ast_dump_emits_readonly_record_pointer_arrow_member_read_when_enabled --test bounded_translation -- --nocapture
git diff --check
```

结果：
- `cargo fmt --check`：exit 0。
- `cargo check --all-targets --all-features`：exit 0。
- `typed-ir`：4 lib tests + 222 bounded tests 通过。
- `typed-ir clang-frontend`：53 lib tests + 397 bounded tests 通过。
- `clang-lowering-report`：63 lib tests + 398 bounded tests 通过。
- `--all-features`：63 lib tests + 398 bounded tests 通过。
- 默认 feature：4 lib tests + 35 bounded tests 通过。
- `clang-frontend`：5 lib tests + 44 bounded tests 通过。
- 真实 clang AST arrow member read smoke：1 passed，使用 `C:\Program Files\LLVM\bin\clang.exe`，并通过 rustc snippet smoke。
- `git diff --check`：exit 0，仅 Windows LF-to-CRLF warnings。

边界：
- 可以说：readonly `const struct T *p` 的简单 `p->scalar_field` read 已能经真实 clang AST lowering -> typed IR -> generic emitter 生成可编译 Rust candidate，Rust 签名使用 `&T`。
- 可以说：真实 clang `RecordDecl` 的完整直接标量字段清单现在能递归附着到 pointer pointee，`Point { x, y }` 不再退化成只含被读取字段的最小 shape。
- 不应说：已支持 C record layout/ABI 等价、semantic acceptance、nullable record pointer、mutable/non-const record pointer read、`p->field = value`、`p->field += value`、`p->field++`、pointer arithmetic record access、alias-sensitive writes、volatile/packed/bitfield/union/nested/anonymous record、非标量字段或完整 pointer ownership model。

English mirror summary:

- Added a narrow generic typed IR candidate path for simple readonly record pointer field reads: `const struct T *p; return p->scalar_field;` now emits `pub fn f(p: &T) -> Scalar { return p.scalar_field; }`.
- Kept arrow member assignment and compound/update write shapes fail-closed with pointer/record ownership evidence errors.
- Made clang record inventory attach to function params and recursively into pointer pointees/array elements, so real clang record pointer candidates can use complete direct scalar field inventories.
- Treated declaration `int` and const-read expression `const int` as compatible for the same integer record field while preserving real type mismatch failures.
- Updated the Chinese and English MVP backlog to mark this narrow readonly pointer field read candidate as supported while keeping pointer field writes and alias-sensitive ownership out of scope.

## 138. 2026-06-28 P1 readonly record pointer null presence checks

本轮继续按多智能体和 TDD 推进 P1 pointer-aware record access 的前置能力。上一节已经支持非 nullable `const struct T *p` 的简单 `p->scalar_field` read；本节不做 flow-sensitive guarded field read，而是先把 readonly record pointer 的 null presence check 打通到 `Option<&T>`，例如 `return p != NULL;` 和 `if (p == NULL) return 0;`。这一步为后续 `if (p == NULL) return ...; return p->x;` 的路径敏感 non-null 证明铺路，但不打开 `Option<&T>` 下的 deref/member use。

核心改动：
- `crates/c2r-translator/src/typed_ir.rs`
  - `emit_nullable_pointer_param_type()` 现在同时支持 readonly integer pointer slice 和 readonly record pointer：前者仍发 `Option<&[T]>`，后者发 `Option<&RecordName>`。
  - `collect_nullable_pointer_params()` 改用 `is_supported_nullable_pointer_type()`，使 `const struct T *p` 在直接 `p == NULL` / `p != NULL` 比较中可被识别为 nullable param。
  - `emit_null_pointer_comparison_condition()` 复用新的 `validate_nullable_pointer_type()`，record pointer 和 integer pointer 的 `.is_none()` / `.is_some()` 发射共用同一条窄路径。
  - nullable pointer 的非 null-comparison 用途仍由 `validate_nullable_pointer_param_uses_in_expr()` 拒绝；因此本节没有放开 nullable `p->x`、`*p`、`p[i]` 或 call-argument escape。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 direct typed IR 正例 `typed_ir_emits_value_comparison_with_record_null_pointer_operand`，验证 `return p != NULL;` 生成 `pub fn has_point(p: Option<&Point>) -> i32` 和 `p.is_some()`。
  - 新增 direct typed IR 正例 `typed_ir_emits_comparison_condition_with_record_null_pointer_operand`，验证 `if (p == NULL)` 生成 `p.is_none()`。
  - 新增真实 clang AST smoke `clang_ast_dump_emits_record_null_pointer_comparison_return_value_when_enabled`，验证 `struct point { int x; }; int has_point(const struct point *p) { return p != NULL; }` 可 lowering 到 typed IR，并由 generic emitter 生成可编译 Rust candidate。
- `docs/c2rust-migration-agent/future-vision-and-mvp.md` 和 `.en.md`
  - 同步标注 readonly record pointer null presence check 已进入 typed IR candidate 子集，同时把下一步明确为 flow-sensitive null-guarded field read。

定向验证：

```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_emits_value_comparison_with_record_null_pointer_operand
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_emits_comparison_condition_with_record_null_pointer_operand
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --manifest-path crates/c2r-translator/Cargo.toml --features "typed-ir clang-frontend" clang_ast_dump_emits_record_null_pointer_comparison_return_value_when_enabled --test bounded_translation -- --nocapture
```

结果：
- direct typed IR value comparison 正例：1 passed，并通过 rustc snippet smoke。
- direct typed IR condition comparison 正例：1 passed，并通过 rustc snippet smoke。
- 真实 clang AST record null pointer comparison smoke：1 passed，使用 `C:\Program Files\LLVM\bin\clang.exe`，并通过 rustc snippet smoke。

边界：
- 可以说：readonly `const struct T *p` 的直接 null presence check 现在会把 Rust 参数建模为 `Option<&T>`，并在 condition/value comparison 中发射 `.is_none()` / `.is_some()`。
- 不应说：已支持 nullable record pointer 的 guarded `p->field` read、path-sensitive non-null refinement、nullable integer slice deref/index、`if (p)`, `p != NULL && p->x`, loop guard、非支配 guard、pointer field writes、alias-sensitive ownership 或 semantic acceptance。
- 下一刀建议：按只读代理建议，先做极窄 flow fact：识别 `if (p == NULL) return ...;` 且 else 为空、then 必定 return，之后只允许 proven-nonnull nullable readonly record pointer 的 direct `p->scalar_field` read，发射 `p.unwrap().field` 或等价 shadow binding。

English mirror summary:

- Added readonly record pointer null-presence candidate generation: `const struct T *p` compared directly with `NULL` now maps to `Option<&T>` and emits `.is_none()` / `.is_some()`.
- Preserved nullable pointer fail-closed behavior for all non-comparison uses, including nullable `p->field`, `*p`, `p[i]`, call-argument escape, and pointer writes.
- Added direct typed IR tests for value and condition comparisons, plus a real clang AST smoke test for `struct point { int x; }; int has_point(const struct point *p) { return p != NULL; }`.
- Updated Chinese and English MVP backlog to make flow-sensitive null-guarded record field reads the next explicit P1 target.

## 139. 2026-06-28 P1 flow-sensitive nullable record pointer field read

本轮继续按多智能体和 TDD 推进 P1 pointer-aware record access，不写 FlashDB/crc32 特例。上一节只把 readonly record pointer 的 null presence check 映射到 `Option<&T>`，并明确不支持 guarded `p->field` read；本节落地极窄的 flow-sensitive non-null 事实：只在直接 `p == NULL` / `p != NULL` guard 能证明当前路径非空时，允许 nullable readonly record pointer 的 direct `p->scalar_field` read。

核心改动：
- `crates/c2r-translator/src/typed_ir.rs`
  - `collect_nullable_pointer_params()` 改为顺序验证函数体，并携带 `proven_nonnull_params` flow state。
  - `validate_nullable_pointer_param_uses_in_stmt()` 对 `if (p != NULL)` 的 then 分支、`if (p == NULL)` 的 else 分支注入 non-null 事实。
  - 新增 `null_return_guard_proves_nonnull()`，仅识别 `if (p == NULL) return ...;` 且 else 为空、then body 恰好直接 return 的窄形态；该 if 之后才把 `p` 视为 non-null。
  - `validate_nullable_pointer_param_uses_in_expr()` 仍默认拒绝 nullable pointer 的普通表达式用途，只额外允许已证明 non-null 的 `IrExpr::Member { is_arrow: true, base: Var(p) }`，且 `p` 必须是 readonly record pointer。
  - 审查后进一步收紧：上述 nullable arrow read 的字段结果也必须是 scalar；即使 guard 已证明 non-null，`p->child_record` 这类非标量字段仍 fail closed。
  - `emit_readonly_record_pointer_member_expr()` 在 nullable record pointer 参数上发射 `p.unwrap().field`；未 nullable 的 readonly record pointer 仍发射 `p.field`。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 direct typed IR 正例 `typed_ir_emits_null_guarded_nullable_record_pointer_arrow_field_read`：`if (p == NULL) return 0; return p->x;` 生成 `Option<&Point>`、`p.is_none()` 和 `p.unwrap().x`。
  - 新增 direct typed IR 正例 `typed_ir_emits_nullable_record_pointer_arrow_field_read_in_nonnull_branch`：`if (p != NULL) return p->x; return 0;` 只在 then 分支允许 `p.unwrap().x`。
  - 新增 direct typed IR 负例覆盖未支配 guard、null 分支读取、guard 后非标量字段读取、inverse guard 后读取，确保 nullable `p->x` 不会被泛化放开。
  - 新增真实 clang AST smoke `clang_ast_dump_emits_null_guarded_readonly_record_pointer_arrow_member_read_when_enabled`，验证真实 C `if (p == NULL) return 0; return p->x;` 可 lowering 到 typed IR，并由 generic emitter 生成可编译 Rust candidate。
- `docs/c2rust-migration-agent/future-vision-and-mvp.md` 和 `.en.md`
  - 同步标注 flow-sensitive null-guarded `p->scalar_field` read 已进入 typed IR candidate 子集；下一步改为 value-position/复杂 target/pointer-alias-sensitive update field write、alias/noalias proof 和 layout/ABI evidence。

定向验证：

```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_emits_null_guarded_nullable_record_pointer_arrow_field_read
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_emits_nullable_record_pointer_arrow_field_read_in_nonnull_branch
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_rejects_nullable_record_pointer_arrow_field_read_without_null_guard
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_rejects_nullable_record_pointer_arrow_field_read_in_null_branch
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_rejects_nullable_record_pointer_arrow_non_scalar_field_read_even_when_guarded
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_rejects_nullable_record_pointer_arrow_field_read_after_inverse_guard
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --manifest-path crates/c2r-translator/Cargo.toml --features "typed-ir clang-frontend" clang_ast_dump_emits_null_guarded_readonly_record_pointer_arrow_member_read_when_enabled --test bounded_translation -- --nocapture
```

结果：
- direct typed IR null-return guard 正例：1 passed，并通过 rustc snippet smoke。
- direct typed IR `p != NULL` then 分支正例：1 passed，并通过 rustc snippet smoke。
- 四个 direct typed IR 负例：均按预期 fail closed。
- 真实 clang AST null-guarded arrow member read smoke：1 passed，使用 `C:\Program Files\LLVM\bin\clang.exe`，并通过 rustc snippet smoke。

边界：
- 可以说：readonly `const struct T *p` 在直接 null guard 后的窄 `p->scalar_field` read 现在能生成 `Option<&T>` + `.is_none()`/`.is_some()` + `unwrap().field` 的可编译 Rust candidate。
- 可以说：当前 non-null 事实是 statement/branch 层面的窄 flow fact，不是通用 pointer analysis。
- 不应说：已支持 C record layout/ABI 等价、semantic acceptance、nullable integer slice deref/index、`if (p)`, `p != NULL && p->x`, loop guard、非支配 guard、复杂 path condition、call-argument escape、pointer field writes、mutable/non-const record pointer read、pointer arithmetic record access、alias-sensitive ownership、volatile/packed/bitfield/union/nested/anonymous record 或完整 pointer ownership model。

English mirror summary:

- Added a narrow flow-sensitive candidate path for nullable readonly record pointer field reads after direct null guards.
- `if (p == NULL) return ...; return p->scalar_field;` and `if (p != NULL) return p->scalar_field; ...` now emit `Option<&T>` plus `.is_none()` / `.is_some()` and `p.unwrap().field`.
- The nullable pointer validator remains fail-closed for ordinary nullable pointer use; only proven-nonnull direct scalar arrow reads on readonly record pointers are allowed.
- Added direct typed IR positive and negative tests, plus a real clang AST smoke test for the null-return guard shape.
- Updated the Chinese and English MVP backlog to mark this narrow guarded-read path as supported while keeping pointer writes, alias-sensitive ownership, layout/ABI claims, and semantic acceptance out of scope.

## 140. 2026-06-28 P1 narrow mutable record pointer field assignment

本轮继续按多智能体和 TDD 推进 P1 pointer/record 写路径，不写 FlashDB/crc32 特例。两个只读代理独立比较了候选切片，结论一致：本轮优先做极窄 `struct T *p; p->scalar_field = scalar;`，因为它直接补上真实 C out-object/state-update 的常见形态；但必须写死为 candidate 生成，不声明 alias/noalias 已解决，也不放开 compound/update、nullable 或多 pointer 情况。

核心改动：
- `crates/c2r-translator/src/typed_ir.rs`
  - `EmitContext` 新增 `mutable_record_pointer_write_params`，由 `collect_mutable_record_pointer_write_params()` 从 assignment target 中收集。
  - 只在 assignment target 是直接 `IrExpr::Member { is_arrow: true, base: Var(p) }`、`p` 是 mutable record pointer 参数、字段结果是 scalar 时收集该参数。
  - 若本函数出现 mutable record pointer field assignment，则要求函数参数列表中 pointer 参数总数恰好为 1；`struct T *p, struct T *q` 或混入 `int *out` / `const struct T *q` 仍 fail closed，错误为缺少 alias proof。
  - `emit_param()` 对被上述 gate 选中的 `struct T *p` 发射 `mut p: &mut T`；integer mutable pointer 仍沿用 `&mut [T]`。
  - `emit_assignment_target()` 的 arrow member target 改走 `emit_mutable_record_pointer_member_assignment_target()`；该 helper 只发射 direct scalar field target `p.field`。
  - `emit_record_definitions()` 和 record field inventory 现在会从 mutable record pointer pointee 合并完整直接标量字段清单，避免只凭被写字段生成最小 shape。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 direct typed IR 正例 `typed_ir_emits_mutable_record_pointer_arrow_field_assignment`：`struct point *p; p->x = value;` 生成 `pub fn set_point_x(mut p: &mut Point, value: i32)` 和 `p.x = value;`。
  - 新增 direct typed IR 负例覆盖多 pointer 参数 alias gate、nullable/null-check 形态、非标量字段、mutable arrow compound shape；原 const pointer arrow assignment 和 const arrow compound shape 仍拒绝。
  - 新增真实 clang AST smoke `clang_ast_dump_emits_mutable_record_pointer_arrow_member_assignment_when_enabled`：真实 C `void set_point_x(struct point *p, int value) { p->x = value; }` 可 lowering 到 typed IR，并由 generic emitter 生成可编译 Rust candidate。
- `docs/c2rust-migration-agent/future-vision-and-mvp.md` 和 `.en.md`
  - 同步标注单 pointer 参数下 mutable `struct T *p` 的直接 `p->scalar_field = scalar` 已进入 typed IR candidate 子集；下一步仍是多 pointer alias/noalias proof、value-position/复杂 target/update field write 和 layout/ABI evidence。

定向验证：

```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_emits_mutable_record_pointer_arrow_field_assignment
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_rejects_mutable_record_pointer_arrow_field_assignment_with_multiple_pointer_params
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_rejects_mutable_record_pointer_arrow_non_scalar_field_assignment
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_rejects_nullable_mutable_record_pointer_arrow_field_assignment
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_rejects_mutable_record_pointer_arrow_field_compound_assignment_shape
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_rejects_record_arrow_field_assignment
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_rejects_record_arrow_field_compound_assignment_shape
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --manifest-path crates/c2r-translator/Cargo.toml --features "typed-ir clang-frontend" clang_ast_dump_emits_mutable_record_pointer_arrow_member_assignment_when_enabled --test bounded_translation -- --nocapture
```

结果：
- direct typed IR mutable record pointer field assignment 正例：1 passed，并通过 rustc snippet smoke。
- alias gate、nullable/null-check、非标量字段、mutable arrow compound shape、const arrow assignment、const arrow compound shape 负例：均按预期 fail closed。
- 真实 clang AST mutable arrow member assignment smoke：1 passed，使用 `C:\Program Files\LLVM\bin\clang.exe`，并通过 rustc snippet smoke。

边界：
- 可以说：单 pointer 参数下的直接 mutable record pointer scalar field assignment 已能从真实 clang AST lowering -> typed IR -> generic emitter 生成可编译 Rust candidate，Rust 签名使用 `&mut T`。
- 可以说：这是一个临时的 single-pointer alias gate，不是通用 alias/noalias proof。
- 不应说：已支持多 pointer alias/noalias、nullable mutable record pointer、`p->field += value`、`p->field++`、`return p->field` 的 mutable pointer read、复杂 base（cast/nested/offset）、pointer arithmetic record access、non-scalar field write、record layout/ABI 等价、semantic acceptance、volatile/packed/bitfield/union/nested/anonymous record 或完整 pointer ownership model。

English mirror summary:

- Added a narrow mutable record pointer field-assignment candidate path: `struct T *p; p->scalar_field = scalar;` now emits `p: &mut T` and `p.scalar_field = scalar;` only when the function has exactly one pointer parameter.
- The single-pointer gate is a conservative candidate precondition, not a general alias/noalias proof.
- Preserved fail-closed behavior for multi-pointer functions, nullable/null-checked mutable pointers, const pointer writes, compound/update arrow writes, non-scalar fields, mutable arrow reads, complex bases, layout/ABI claims, and semantic acceptance.
- Added direct typed IR positive/negative tests and a real clang AST smoke test for `void set_point_x(struct point *p, int value) { p->x = value; }`.
- Updated the Chinese and English MVP backlog to mark this narrow write path as supported while keeping the broader pointer/alias-sensitive field-write work open.

## 141. 2026-06-28 P1 narrow mutable record pointer field compound assignment

本轮继续按多智能体和 TDD 推进 P1 pointer/record 写路径，不写 FlashDB/crc32 特例。两个只读代理给出不同优先级建议：一个认为 B（写后一般 `return p->field` 读）更像基础对象模型，另一个建议先做 A（`p->field += value`）且保持极窄。主线选择更保守的 A：只支持 standalone、直接 target、简单 RHS 的 mutable record pointer field compound assignment，不打开一般 mutable arrow read。

核心改动：
- `crates/c2r-translator/src/typed_ir.rs`
  - `IrStmt::Assign` 在普通 `emit_expr_with_prelude()` 前增加专用 helper：只识别 `target = Binary(same_direct_arrow_member_target, op, simple_rhs)`。
  - 复用上一节的 single-pointer mutable record pointer write gate：只有函数 pointer 参数总数恰好为 1，且 target 是直接 `IrExpr::Member { is_arrow: true, base: Var(p) }` 的 scalar field 时，`struct T *p` 才会发射为 `mut p: &mut T`。
  - 专用 helper 发射 `p.field = (p.field + rhs);`，因此 `p->field += value` 形态可通过，但 `return p->field`、普通 RHS 里的 `p->field`、复杂 base/cast/offset 仍走原有 fail-closed 路径。
  - RHS guard 只允许 integer variable、integer literal、integral cast 包裹的简单值；`value + 1`、call、member/index/deref、inc/dec 等复杂 RHS 仍拒绝。
- `crates/c2r-translator/src/clang_frontend.rs`
  - `compound_assignment_target_type()` 对 direct mutable record pointer arrow field 返回 field type，但仍拒绝 const pointer、复杂 base 和非 record pointer。
  - 将已有 record field compound RHS guard 从 by-value `p.x += value` 扩展到 direct mutable arrow `p->x += value`，保持 skeleton path 和 real clang AST path 一致。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 把上一节的 mutable arrow compound 负例改为正例 `typed_ir_emits_mutable_record_pointer_arrow_field_compound_assignment_shape`。
  - 新增 direct typed IR 负例 `typed_ir_rejects_mutable_record_pointer_arrow_field_compound_assignment_complex_rhs`，确保复杂 RHS 仍 fail closed。
  - 保留 `typed_ir_rejects_mutable_record_pointer_arrow_field_read_after_assignment`，确保写后一般 mutable arrow read 没有被顺手放开。
  - 把 clang skeleton arrow compound 负例改为正例 `clang_lowering_skeleton_maps_mutable_record_pointer_field_compound_assignment`。
  - 新增真实 clang AST smoke `clang_ast_dump_emits_mutable_record_pointer_field_compound_assignment_when_enabled` 和复杂 RHS 负例 `clang_ast_dump_rejects_mutable_record_pointer_field_compound_assignment_complex_rhs_when_enabled`。
- `docs/c2rust-migration-agent/future-vision-and-mvp.md` 和 `.en.md`
  - 同步标注单 pointer 参数下 mutable `struct T *p` 的直接 `p->scalar_field = scalar` 和简单 standalone `p->scalar_field += scalar` 已进入 typed IR candidate 子集；后续仍优先做 mutable field read-after-write、多 pointer alias/noalias proof、value-position/复杂 target/field inc-dec 和 layout/ABI evidence。

定向验证：

```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_emits_mutable_record_pointer_arrow_field_compound_assignment_shape --test bounded_translation -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_rejects_mutable_record_pointer_arrow_field_compound_assignment_complex_rhs --test bounded_translation -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features "typed-ir clang-frontend" clang_lowering_skeleton_maps_mutable_record_pointer_field_compound_assignment --test bounded_translation -- --nocapture
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --manifest-path crates/c2r-translator/Cargo.toml --features "typed-ir clang-frontend" clang_ast_dump_emits_mutable_record_pointer_field_compound_assignment_when_enabled --test bounded_translation -- --nocapture
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --manifest-path crates/c2r-translator/Cargo.toml --features "typed-ir clang-frontend" clang_ast_dump_rejects_mutable_record_pointer_field_compound_assignment_complex_rhs_when_enabled --test bounded_translation -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_rejects_mutable_record_pointer_arrow_field_read_after_assignment --test bounded_translation -- --nocapture
```

结果：
- direct typed IR mutable record pointer field compound assignment 正例：1 passed，并通过 rustc snippet smoke。
- direct typed IR complex RHS 负例：1 passed，错误原因包含 `mutable record pointer field compound assignment RHS`。
- clang skeleton mutable arrow compound 正例：1 passed，并通过 rustc snippet smoke。
- 真实 clang AST mutable arrow compound 正例/复杂 RHS 负例：均 1 passed，使用 `C:\Program Files\LLVM\bin\clang.exe`。
- 写后一般 `return p->field` mutable arrow read 负例：1 passed，仍按 `struct point *` arrow read unsupported 拒绝。

边界：
- 可以说：单 pointer 参数下的直接 mutable record pointer scalar field compound assignment（例如 `p->x += value`）已能从真实 clang AST lowering -> typed IR -> generic emitter 生成可编译 Rust candidate，Rust 签名使用 `&mut T`。
- 可以说：这是 value-discarded standalone statement 的窄 candidate path，正确性仍要靠后续验证门禁，不是 semantic acceptance。
- 不应说：已支持一般 mutable `p->field` read、read-after-write 对象模型、多 pointer alias/noalias、nullable mutable pointer、value-position compound assignment、`p->field++`、复杂 RHS/target、integer promotion/truncation 组合、pointer arithmetic record access、record layout/ABI 等价、semantic acceptance、volatile/packed/bitfield/union/nested/anonymous record 或完整 pointer ownership model。

English mirror summary:

- Added a narrow mutable record pointer field compound-assignment candidate path: `struct T *p; p->scalar_field += scalar;` now emits `p: &mut T` and `p.scalar_field = (p.scalar_field + scalar);` only under the existing single-pointer-param gate.
- The implementation does not globally enable mutable arrow field reads. It special-cases only assignment values shaped as `target = Binary(same_direct_arrow_member_target, op, simple_rhs)`.
- Kept fail-closed behavior for complex RHS/targets, nullable mutable pointers, multi-pointer functions, `return p->field`, `p->field++`, value-position compound assignment, layout/ABI claims, and semantic acceptance.
- Extended clang skeleton and real clang AST lowering to admit direct mutable record pointer arrow compound targets while applying the same simple-RHS record-field guard used for by-value `p.x += value`.
- Updated the Chinese and English MVP backlog to mark this narrow compound write path as supported while keeping mutable read-after-write, alias/noalias proof, field inc-dec, and broader pointer ownership modeling open.

## 142. 2026-06-28 P1 narrow mutable record pointer field read-after-write

本轮继续按多智能体和 TDD 推进 P1 pointer/record 写后读路径。两个只读代理确认：clang lowering 已能把 `p->x = value; return p->x;` 解析成 `Assign(Member arrow)` + `Return(Member arrow)`，主要缺口在 typed IR emitter；同时必须避免把整个 `struct T *p` 的一般 field read 打开。主线实现为字段级、顺序敏感的窄 candidate：只有同一个 direct scalar field 在当前路径之前已经 definite written，才允许读取。

核心改动：
- `crates/c2r-translator/src/typed_ir.rs`
  - `DefiniteAssignmentState` 新增 mutable record pointer field 状态，按 `(base, field)` 追踪已 definite written 的字段，而不是只按参数 `p` 放开。
  - `validate_definite_assignment()` 现在返回通过校验的 mutable record pointer read field 集合，并写回 `EmitContext.mutable_record_pointer_read_fields`。
  - assignment target 是 direct mutable record pointer field 时，先校验 RHS，再把该 `(p, field)` 标记为已写；`p->x += value` 仍通过上一节的 compound 专用逻辑跳过自身 lhs 旧值读取。
  - `if` 分支后只保留 before 已写或 then/else 两边都写过的字段；`while`/`for`/`do while` 不把循环体内写入提升为循环后的 definite write。
  - `emit_member_expr()` 先尝试 `emit_mutable_record_pointer_member_expr()`：只有 base 是已声明 direct `Var(p)`、`p` 通过 single-pointer mutable write gate、field 是 scalar、且 validator 已登记该 `(p, field)` 可读时，才发射 `p.field`；否则继续走 readonly record pointer 路径或 fail closed。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 将 `typed_ir_rejects_mutable_record_pointer_arrow_field_read_after_assignment` 改为正例 `typed_ir_emits_mutable_record_pointer_arrow_field_read_after_assignment`，覆盖 `p->x = value; return p->x;`。
  - 新增 direct typed IR 负例：read-before-write、maybe-write 后读取、写 `x` 后读 `y`。
  - 新增真实 clang AST smoke：`clang_ast_dump_emits_mutable_record_pointer_field_read_after_assignment_when_enabled`。
  - 新增真实 clang AST 负例：`clang_ast_dump_rejects_mutable_record_pointer_field_read_before_assignment_when_enabled`。
- `docs/c2rust-migration-agent/future-vision-and-mvp.md` 和 `.en.md`
  - 同步标注 single-pointer gate 下同字段 definite write 后的 mutable `p->scalar_field` read 已进入 typed IR candidate 子集；后续仍优先做多 pointer alias/noalias proof、value-position/复杂 target/field inc-dec、path-sensitive mutable field definite assignment 和 layout/ABI evidence。

定向验证：

```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_emits_mutable_record_pointer_arrow_field_read_after_assignment --test bounded_translation -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_rejects_mutable_record_pointer_arrow_field_read_before_assignment --test bounded_translation -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_rejects_mutable_record_pointer_arrow_field_read_after_maybe_assignment --test bounded_translation -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_rejects_mutable_record_pointer_arrow_different_field_read_after_assignment --test bounded_translation -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_emits_mutable_record_pointer_arrow_field_compound_assignment_shape --test bounded_translation -- --nocapture
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --manifest-path crates/c2r-translator/Cargo.toml --features "typed-ir clang-frontend" clang_ast_dump_emits_mutable_record_pointer_field_read_after_assignment_when_enabled --test bounded_translation -- --nocapture
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --manifest-path crates/c2r-translator/Cargo.toml --features "typed-ir clang-frontend" clang_ast_dump_rejects_mutable_record_pointer_field_read_before_assignment_when_enabled --test bounded_translation -- --nocapture
```

结果：
- direct typed IR 写后读正例：1 passed，并通过 rustc snippet smoke。
- direct typed IR read-before-write、maybe-write 后读取、写 `x` 后读 `y` 负例：均 1 passed，错误原因包含 `mutable record pointer field p.<field> is read before definite assignment`。
- 复合赋值回归 `p->x += value`：1 passed。
- 真实 clang AST 写后读正例/读前写负例：均 1 passed，使用 `C:\Program Files\LLVM\bin\clang.exe`。

边界：
- 可以说：single-pointer gate 下 direct mutable record pointer scalar field 在同字段 definite write 后可以读取，例如 `p->x = value; return p->x;` 生成 `p: &mut T` 和 `return p.x;`。
- 可以说：这是字段级 definite assignment，不是通用 alias/noalias proof，也不是完整 C object model。
- 不应说：已支持未写先读、maybe-write 后读取、跨循环/复杂 path condition 后读取、多 pointer alias/noalias、nullable mutable pointer、复杂 base、field pointer arithmetic、non-scalar field、`p->field++`、value-position compound assignment、record layout/ABI 等价、semantic acceptance、volatile/packed/bitfield/union/nested/anonymous record 或完整 pointer ownership model。

English mirror summary:

- Added a narrow mutable record pointer field read-after-write candidate path.
- `struct T *p; p->scalar_field = value; return p->scalar_field;` now emits `p: &mut T`, `p.scalar_field = value;`, and `return p.scalar_field;` only when the same direct scalar field has been definitely written earlier on the current path.
- The definite-write state is field-level: `p->x = value; return p->y;` still fails closed.
- Reads before writes and reads after maybe-writes still fail closed; loop/body writes are not promoted to post-loop definite writes.
- Updated Chinese and English MVP backlog to move this narrow read-after-write path into the supported typed IR candidate subset while keeping broader alias/noalias and path-sensitive ownership work open.

## 143. 2026-06-28 P1 mutable record pointer field statement inc/dec

本轮继续按多智能体和 TDD 推进 P1 pointer/record 写路径，不写 FlashDB/crc32 特例。两个只读代理结论一致：`p->x++` / `--p->x` 不需要新增 typed IR raw inc/dec emitter；更安全的切口是只在 clang statement-position、表达式值被丢弃时，把 direct mutable record pointer scalar field inc/dec desugar 成现有 assignment/update 形状：`p->x = p->x +/- 1`。这复用上一节的 single-pointer gate、field-level definite-write/read 逻辑和 mutable arrow compound update helper。

核心改动：
- `crates/c2r-translator/src/clang_frontend.rs`
  - `inc_dec_assignment_target_type()` 放开 direct mutable record pointer arrow field，但仅限 `context == "statement"`。
  - arrow base 必须是 direct `DeclRef`，并且类型必须满足非 const record pointer；`const struct T *p`、复杂 base、非 record pointer base 仍 fail closed。
  - `ForStmt step` context 继续拒绝 record pointer field inc/dec，避免把 loop step 顺序语义混入本切口。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 direct typed IR 正例 `typed_ir_emits_mutable_record_pointer_arrow_field_inc_dec_desugar_shape`，直接验证 `Assign(Member arrow, Binary(Add/Sub, same Member, 1))` 可发射 `p: &mut Point` 和 `p.x = (p.x +/- 1i32);`。
  - 新增 direct typed IR 负例 `typed_ir_rejects_mutable_record_pointer_arrow_field_raw_inc_dec_expr`，先 definite-write 字段后再构造 raw `IrExpr::IncDec(Member arrow)`，确认 raw inc/dec expression 仍 fail closed。
  - 将真实 clang smoke 改为正例 `clang_ast_dump_emits_mutable_record_pointer_field_inc_dec_statement_when_enabled`，覆盖 `p->x++; ++p->x; p->x--; --p->x;`。
  - 新增 clang frontend unit 边界：const record pointer field inc/dec 和 `ForStmt step` 中 record pointer field inc/dec 仍拒绝。
- `docs/c2rust-migration-agent/README.md` / `.en.md`、`core-translation-architecture.md` / `.en.md`、`COVERAGE.md` / `.en.md`、`future-vision-and-mvp.md` / `.en.md`
  - 同步把 direct single-pointer mutable record pointer scalar field statement inc/dec 标为窄 candidate 子集。
  - 明确 raw/value-position inc/dec、`return p->x++`、`for (...; p->x++)`、多 pointer alias、nullable mutable pointer、复杂 base/target/RHS、non-scalar field、layout/ABI 和 semantic acceptance 仍 fail closed。

定向验证：
```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features "typed-ir clang-frontend" stmt_skeleton_from_ast_accepts_mutable_record_pointer_field_inc_dec_statement_as_assignment -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features "typed-ir clang-frontend" stmt_skeleton_from_ast_rejects_const_record_pointer_field_inc_dec_statement -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features "typed-ir clang-frontend" for_step_stmt_skeleton_from_ast_rejects_record_pointer_field_inc_dec_step -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_emits_mutable_record_pointer_arrow_field_inc_dec_desugar_shape -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_rejects_mutable_record_pointer_arrow_field_raw_inc_dec_expr -- --nocapture
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --manifest-path crates/c2r-translator/Cargo.toml --features "typed-ir clang-frontend" clang_ast_dump_emits_mutable_record_pointer_field_inc_dec_statement_when_enabled -- --nocapture
```

结果：
- clang frontend statement/const/for-step 单元测试均按预期通过。
- direct typed IR desugar 正例通过，并通过 rustc snippet smoke。
- raw `IrExpr::IncDec(Member arrow)` 负例通过，错误保持在 `inc/dec expression is unsupported`。
- 真实 clang AST `p->x++; ++p->x; p->x--; --p->x;` smoke 通过，使用 `C:\Program Files\LLVM\bin\clang.exe`，并通过 rustc snippet smoke。

边界：
- 可以说：single-pointer gate 下的 direct mutable record pointer scalar field 在 standalone statement 位置支持 `p->x++` / `++p->x` / `p->x--` / `--p->x`，并发射为 `p.x = (p.x +/- 1i32);`。
- 可以说：这是 clang statement desugar 后的 assignment/update candidate，不是完整 C inc/dec expression semantics。
- 不应说：已支持 raw/value-position inc/dec、`return/call/condition` 中的 `p->field++`、`ForStmt` step 中 record-field inc/dec、多 pointer alias/noalias、nullable mutable pointer、复杂 base/target/RHS、non-scalar field、record layout/ABI 等价、semantic acceptance、volatile/packed/bitfield/union/nested/anonymous record 或完整 pointer ownership model。

English mirror summary:

- Added a narrow mutable record pointer field statement-inc/dec candidate path.
- `struct T *p; p->scalar_field++; ++p->scalar_field; p->scalar_field--; --p->scalar_field;` now lowers from real clang AST into assignment desugar shapes and emits `p: &mut T` plus direct Rust field updates, under the existing single-pointer-param gate.
- Raw `IrExpr::IncDec` is still unsupported; value-position inc/dec, `ForStmt` step record-field inc/dec, complex targets, nullable mutable pointers, multi-pointer aliasing, layout/ABI claims, and semantic acceptance remain fail-closed.
- Updated Chinese and English docs/coverage/backlog to mark this narrow statement-position path as supported while keeping broader pointer ownership and value-position update semantics open.

## 144. 2026-06-28 P1 mutable record pointer field if-return definite assignment

本轮继续按多智能体和 TDD 推进 P1 pointer/record 读路径，不写 FlashDB/crc32 特例。只读代理一致建议：上一节的字段级 definite-write/read 仍过于保守，`if (cond) { p->x = value; } else { return 0; } return p->x;` 这类真实 C 叶子函数应进入 generic typed IR candidate；但不能把它写成通用 path-sensitive 或通用 alias 支持。主线实现为极窄的 branch merge：只有会继续执行的路径都写入同一个字段，未写入路径能被当前 guard 证明直接 return，后续读取才可通过。

核心改动：
- `crates/c2r-translator/src/typed_ir.rs`
  - 新增 `body_definitely_returns()` / `stmt_definitely_returns()`，目前只有直接 `Return` 和 then/else 两边都 definite-return 的 `If` 算作分支级返回证明。
  - 新增 `merge_definite_branch_set()`，用于合并 scalar local initialized 集合和 mutable record pointer field definite-write 集合。
  - `IrStmt::If` 的 definite-assignment merge 现在区分 fallthrough 和 returning 分支：returning 分支不要求提供后续事实，但也不会把只在 returning 分支里写入的事实带到后续路径。
  - both branches return 时只保留 `before`，避免 unreachable 后续代码拿到虚假的新事实。
  - branch-local scalar declarations 仍不会泄漏到父作用域。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 direct typed IR 正例 `typed_ir_emits_mutable_record_pointer_arrow_field_read_after_if_else_return`。
  - 新增 direct typed IR 正例 `typed_ir_emits_mutable_record_pointer_arrow_field_read_after_if_then_return_else_write`。
  - 新增 direct typed IR 正例 `typed_ir_emits_uninitialized_scalar_local_after_if_return_assignment`，因为 scalar initialized 集合复用同一合并逻辑。
  - 新增 direct typed IR 负例覆盖 returning 分支读早于写、只在 returning 分支写入、loop-body return 不算分支级 return。
  - 新增真实 clang AST smoke `clang_ast_dump_emits_mutable_record_pointer_field_read_after_if_else_return_when_enabled`。
- `docs/c2rust-migration-agent/README.md` / `.en.md`、`COVERAGE.md` / `.en.md`、`core-translation-architecture.md` / `.en.md`、`future-vision-and-mvp.md` / `.en.md`
  - 同步标注 direct if-return fallthrough write 已进入窄 typed IR candidate 子集。
  - 明确普通 maybe-write、只在 returning 分支写入、loop/复杂路径 return、多 pointer alias、nullable mutable pointer、复杂 base/target/RHS、layout/ABI 和 semantic acceptance 仍 fail closed。

定向验证：
```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_emits_mutable_record_pointer_arrow_field_read_after_if_else_return -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir read_after_if -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_emits_uninitialized_scalar_local_after_if_return_assignment -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_rejects_mutable_record_pointer_arrow_field_read_when_only_returning_branch_writes -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_rejects_mutable_record_pointer_arrow_field_read_after_loop_return_branch -- --nocapture
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --manifest-path crates/c2r-translator/Cargo.toml --features "typed-ir clang-frontend" clang_ast_dump_emits_mutable_record_pointer_field_read_after_if_else_return_when_enabled -- --nocapture
```

结果：
- RED 已观察：新增正例在实现前按 `mutable record pointer field p.x is read before definite assignment` 失败。
- direct typed IR if-else-return / then-return-else-write 正例均通过，并通过 rustc snippet smoke。
- scalar local if-return assignment 正例通过，并通过 rustc snippet smoke。
- returning branch read-before-write、returning-branch-only write、loop-body return 负例均按预期 fail closed。
- 真实 clang AST `if (cond) { p->x = value; } else { return 0; } return p->x;` smoke 通过，使用 `C:\Program Files\LLVM\bin\clang.exe`，并通过 rustc snippet smoke。

边界：
- 可以说：single-pointer gate 下，direct mutable record pointer scalar field 的同字段读取现在支持一个窄化 if-return 分支公差：all fallthrough paths write; non-writing branches must definitely return。
- 可以说：无初始化 scalar local 的 assignment-before-read proof 也获得同样的窄化 if-return 分支合并。
- 不应说：已支持通用 path-sensitive definite assignment、通用 maybe-write、通用 alias/noalias、nullable mutable pointer、loop/CFG return proof、复杂 base/target/RHS、field pointer arithmetic、non-scalar field、record layout/ABI 等价、semantic acceptance、volatile/packed/bitfield/union/nested/anonymous record 或完整 pointer ownership model。

English mirror summary:

- Added a narrow if-return definite-assignment merge for mutable record pointer field reads.
- `if (cond) { p->scalar_field = value; } else { return 0; } return p->scalar_field;` now emits `p: &mut T` and `return p.scalar_field;` only when every fallthrough path writes the same direct scalar field and the non-writing branch definitely returns.
- The same merge improves uninitialized scalar local assignment-before-read for direct if-return shapes.
- Writes that occur only on returning branches, reads before writes, ordinary maybe-writes, loop/complex-path returns, nullable mutable pointers, multi-pointer aliasing, complex targets/RHS, layout/ABI claims, and semantic acceptance remain fail-closed.
- Updated Chinese and English docs/coverage/backlog to move this narrow direct if-return path into the supported typed IR candidate subset while keeping broader path-sensitive/CFG and alias work open.

## 145. 2026-06-28 external review triage: route/wrapping/competition clang

本轮收到外部评价，主线和 3 个只读代理做了代码核查。结论如下：

- route 评价基本成立：`crates/c2r-translator/src/translation_route.rs` 目前只有 `GenericTypedIr` / `Unsupported` 两个 route，以及 `GenericTypedIrEmitter` / `None` 两个 generator；`generic_typed_ir_route()` 和 `unsupported_route()` 是静态 metadata 构造器。`emit_rust_from_ir()` / `emit_rust_from_ir_with_globals()` 只是 emitter 成功贴 `GenericTypedIr`，失败贴 `Unsupported`。这不是多候选调度器，更准确说是 typed IR candidate provenance。
- legacy fallback 评价方向成立但位置要修正：不是 `lib.rs` 直接 `.unwrap_or_else(legacy)`，实际在 `crates/c2r-translator/src/artifacts.rs` 的 `translate_slice_with_optional_clang_lowered_ir()`：`try_translate_slice_with_clang_lowered_ir(spec).unwrap_or_else(|| translate_slice(spec))`。启用 lowering report 时会另写 artifact，但主翻译结果存在静默 fallback 风险。
- pipeline route-decision 有规则门禁和 L0/L1/L2/L4 映射，但仍不是候选生成前的真选择引擎；它没有候选列表、score、fallback chain 或 C2Rust/LLM 调度。
- unsigned wrapping 评价成立且优先级最高：`emit_binary_op()` 对 `Add` / `Sub` / `Mul` 发裸 `+` / `-` / `*`；`uint32_t` 等 C unsigned arithmetic 需要模 `2^n`，而 Rust debug/overflow-checks 下裸运算会 panic。主线用 `rustc -C overflow-checks=on` 复现 `0u32 - 1u32` runtime panic。shift 要分开处理：合法 shift count 的 Rust/C unsigned 结果通常一致，非法 shift count 在 C 中本来就是 UB，因此这是 contract/fail-closed 问题，不是 wrapping 替换问题。
- competition clang 评价要修正措辞：`config/competition-env/environment.json` 没有把 clang 列为 baseline tool，也没有声明 clang not_found；`cmake` 才明确 unavailable。`auto_migrate.py --emit-clang-lowering-report` 是 opt-in，不传时不会启用 typed IR clang lowering feature。结论是必须显式声明/安装/检测 `CLANG_PATH` 和比赛 clang lane，不能静默依赖本机 Windows clang。

已同步待办：
- `docs/c2rust-migration-agent/future-vision-and-mvp.md` / `.en.md` P0 新增 competition clang lane。
- P0 新增 unsigned integer modulo semantics 修复项，要求先加 debug/overflow-checks runtime RED tests，再发射 wrapping 或等价策略。
- P0 新增 route metadata/provenance 与真 candidate-selection layer 的边界项，要求禁止无遥测静默 fallback。
- P2 新增多候选 router 研究项，明确只能在 P0 语义稳定后做，且不能替代 C oracle。

下一刀建议：
1. 先提交当前 if-return definite-assignment 切片。
2. 下一提交优先做 unsigned wrapping 红测和修复：新增运行 emitted Rust snippet 的测试 helper，覆盖 `u32::MAX + 1`, `0u32 - 1`, unsigned multiply。修复应只对 unsigned `Add` / `Sub` / `Mul` 使用 wrapping；signed overflow、division/modulo zero、invalid shift count 继续 fail closed 或进入后续 contract。
3. 再做 competition clang lane：明确 `optional_tools.clang` 或 required clang 配置，补 `CLANG_PATH` 检查和 opt-in wrapper。

## 146. 2026-06-28 P0 unsigned arithmetic wrapping semantics

本轮按外部评价和多智能体只读审计修复 P0 语义 bug：typed IR emitter 过去对 C unsigned `+` / `-` / `*` 发裸 Rust 运算，导致 debug/overflow-checks 下 `uint32_t` 模运算候选会 panic，而 release 下才碰巧回绕。这会直接影响 adler32、crc32、xxhash、checksum/hash 类真实题型，不能依赖编译 profile。

核心改动：
- `crates/c2r-translator/src/typed_ir.rs`
  - 新增 `emit_binary_result_expr()` / `unsigned_wrapping_method()` / `is_unsigned_integer_type()`。
  - 普通 `IrExpr::Binary`、`emit_expr_with_prelude()` 中的 binary 表达式、以及 mutable record pointer field compound assignment 的专用发射路径，现在共享同一策略。
  - 仅当 result type 是 unsigned integer 且 op 是 `Add` / `Sub` / `Mul` 时发射 `.wrapping_add(...)` / `.wrapping_sub(...)` / `.wrapping_mul(...)`。
  - signed `+` / `-` / `*`、shift、division、modulo、bitwise 继续保留原有发射边界；signed overflow、division/modulo zero、invalid shift count 是后续 contract/fail-closed 问题。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 `assert_rust_snippet_runs()`，用 `rustc -C overflow-checks=on` 编译并运行 emitted Rust snippet。
  - 新增运行型 RED/GREEN 用例：`u32::MAX + 1 -> 0`、`0u32 - 1 -> u32::MAX`、`u32::MAX * 2 -> 0xFFFF_FFFE`。
  - 更新无符号 `usize`/`u32` 旧字符串断言为 `wrapping_add` 形状；legacy string translator 的字符串断言不动。
- 文档同步：
  - `README.md`
  - `docs/c2rust-migration-agent/README.md` / `.en.md`
  - `COVERAGE.md` / `.en.md`
  - `core-translation-architecture.md` / `.en.md`
  - `future-vision-and-mvp.md` / `.en.md`

已观察 RED：
```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir wrapping_semantics -- --nocapture
```
实现前 3 条测试分别因 `attempt to add/subtract/multiply with overflow` 失败。

已跑定向 GREEN：
```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir wrapping_semantics -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir --test bounded_translation typed_ir_ -- --nocapture
```
结果：3 条 wrapping runtime tests 通过；216 条 `typed_ir_` 集成测试通过。

边界：
- 可以说：typed IR generic emitter 的 unsigned integer `Add` / `Sub` / `Mul` candidate 不再依赖 debug/release overflow 行为。
- 可以说：checksum/hash 类候选生成少了一个核心 profile-dependent 正确性风险。
- 不应说：已完成 adler/crc/xxhash 全语义接受、完整 C arithmetic、signed overflow parity、非法 shift count 处理、division/modulo zero contract、完整 usual arithmetic conversions、pointer arithmetic 或 semantic acceptance。

English mirror summary:

- Fixed the typed IR emitter's profile-dependent C unsigned arithmetic lowering for `+`, `-`, and `*`.
- Unsigned-result `IrExpr::Binary` now emits explicit Rust `wrapping_add`, `wrapping_sub`, and `wrapping_mul` across the normal expression path, the prelude expression path, and the mutable record pointer field compound-update helper.
- Added runtime emitted-Rust tests compiled with `rustc -C overflow-checks=on` for `u32::MAX + 1`, `0u32 - 1`, and unsigned multiply.
- Signed overflow, division/modulo zero, invalid shift counts, full usual arithmetic conversions, pointer arithmetic, and semantic acceptance remain separate fail-closed or validation-gate work.

## 147. 2026-06-28 P0 competition clang lane explicit opt-in

本轮承接第 145 节 P0 待办，明确比赛环境里的 clang 路线，而不是继续让本机 Windows clang 或 diagnostic lowering report 语义混在默认 lane 里。

设计选择：
- clang 不进入默认必需 toolchain；默认构建、测试、验证仍不要求 clang。
- `config/competition-env/environment.json` 新增 `optional_tools.clang` 和 `optional_lanes.competition_clang`，声明 `CLANG_PATH` 是该 lane 的必需环境变量，`LIBCLANG_PATH` 只是可选环境变量。
- 新增 `auto_migrate.py --competition-clang-lane` 作为比赛 typed-IR clang lane wrapper。该 flag 会隐式启用 `--emit-clang-lowering-report`，并在运行 translator 前 fail-fast 检查 `CLANG_PATH`。
- 保留原有 `--emit-clang-lowering-report` 诊断语义：缺 `CLANG_PATH` 时仍可产出 `status=unavailable` / `missing_clang_path` report，不让默认非 clang lane 失败。

核心改动：
- `validation/tools/auto_migrate.py`
  - 新增 `--competition-clang-lane`。
  - 新增 `require_competition_clang_lane()`。
  - `cache_identity()` / `emit_cache_metadata()` 内部使用 effective lowering flag：`emit_clang_lowering_report or competition_clang_lane`，避免只有 `main()` 改写参数时才记录证据。
  - `clang_lowering_identity(..., competition_clang_lane=True)` 会记录 `lane=competition-clang-lane`、`required=true`、`requires_env=["CLANG_PATH"]`、`optional_env=["LIBCLANG_PATH"]`。
- `validation/tools/test_auto_migrate.py`
  - 新增/强化 `test_competition_clang_lane_requires_clang_path`。
  - `test_cache_identity_records_competition_clang_lane` 现在只传 `competition_clang_lane=True`，并断言 command args、feature set 和 lane identity 都完整记录。
- `config/competition-env/environment.json` 与兼容 profile 同步新增 optional clang lane。
- `validation/tools/test_competition_environment_profile.py`
  - 覆盖 `optional_tools.clang` 和 `optional_lanes.competition_clang`。
- `config/competition-env/README.md` / `.en.md`、`docs/c2rust-migration-agent/future-vision-and-mvp.md` / `.en.md`
  - 同步说明 clang 是 explicit opt-in，不是默认 baseline requirement。

已观察 RED：
```powershell
python -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_competition_clang_lane_requires_clang_path
python -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_cache_identity_records_competition_clang_lane validation.tools.test_competition_environment_profile.CompetitionEnvironmentProfileTests.test_competition_environment_profile_records_clang_lane_identity
```
实现前分别因 argparse 不认识 `--competition-clang-lane`、`cache_identity()` 不认识 `competition_clang_lane`、以及 profile 缺 `optional_lanes` 失败。

已跑定向 GREEN：
```powershell
python -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_cache_identity_records_competition_clang_lane validation.tools.test_auto_migrate.AutoMigrateTests.test_competition_clang_lane_requires_clang_path validation.tools.test_competition_environment_profile.CompetitionEnvironmentProfileTests.test_competition_environment_profile_records_clang_lane_identity validation.tools.test_competition_environment_profile.CompetitionEnvironmentProfileTests.test_default_profile_matches_competition_baseline validation.tools.test_competition_environment_profile.CompetitionEnvironmentProfileTests.test_compatibility_profile_stays_synchronized_with_default_profile
```
结果：5 tests OK。

边界：
- 可以说：比赛 clang typed-IR lane 现在是显式 opt-in，缺 `CLANG_PATH` 会清晰失败。
- 可以说：默认非 clang lane、普通 `--emit-clang-lowering-report` 诊断 lane 和 toolchain check 默认要求没有被改变。
- 不应说：比赛环境默认已有 clang、libclang parse 路线已启用、typed IR candidate 已自动成为 semantic pass、或 route metadata 已升级成真正多候选 router。

English mirror summary:

- Added an explicit `--competition-clang-lane` for the competition typed-IR clang path.
- The lane implicitly enables `clang-lowering-report`, requires `CLANG_PATH`, and fails clearly when `CLANG_PATH` is missing.
- Default build/test/validation paths still do not require clang, and plain `--emit-clang-lowering-report` remains diagnostic-only when clang is missing.
- Competition environment JSON now records clang as an optional tool/lane, with synchronized compatibility profile and bilingual docs.

## 148. 2026-06-28 P0 explicit fallback provenance

本轮继续处理外部评价中“route/fallback 仍像空壳”的核心问题，选择最小可提交切片：不一次性实现完整 C2Rust/LLM 多候选 router，而是先消除 `clang-lowering-report` feature 下 clang-lowered typed IR 失败后 fallback 到 legacy string translator 的无遥测风险。

核心改动：
- `crates/c2r-translator/src/model.rs`
  - 新增 `TranslationSource`，记录主 Rust draft 的 `selected` generator，并可记录 `fallback_from` / `fallback_reason`。
- `crates/c2r-translator/src/legacy_translation.rs`
  - legacy string translator 正常生成时标记 `selected=legacy-string-translator`。
- `crates/c2r-translator/src/clang_lowered_translation.rs`
  - clang-lowered typed IR 成功生成时标记 `selected=clang-lowered-typed-ir`。
- `crates/c2r-translator/src/artifacts.rs`
  - `translate_slice_with_optional_clang_lowered_ir()` 保留 compatibility fallback，但 fallback 结果现在标记为 `selected=legacy-string-translator`、`fallback_from=clang-lowered-typed-ir`、`fallback_reason=clang_lowered_typed_ir_unavailable`。
  - raw `auto-translation-plan.json` 写入 `translation_source`。
  - raw `auto-translation-events.jsonl` 在 fallback 时追加 `translation_fallback` 事件。
- `validation/tools/auto_migrate.py`
  - `normalize_translation_artifacts()` 归一化后保留 `translation_source`。
  - `candidate_generation_evidence()` 写入 `primary_candidate`，使 `route_decision.candidate_generation.primary_candidate` 可审计主候选来源。
  - 归一化后的 events 在 fallback 时也写入 `event_kind=translation_fallback`，避免覆盖 Rust raw events 后丢遥测。
- `validation/auto-translation-template/route-decision.schema.json` 与 `validation-profile.schema.json`
  - 为 `candidate_generation.primary_candidate` 增加 schema 形状。
- 文档同步：
  - `docs/c2rust-migration-agent/future-vision-and-mvp.md` / `.en.md`
  - `docs/c2rust-migration-agent/README.md` / `.en.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.md` / `.en.md`

已观察 RED：
```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_lowering_fallback_to_legacy_is_recorded_in_plan_and_events -- --nocapture
```
实现前失败于 `translation_source.selected == Null`。

```powershell
python -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_route_decision_records_primary_candidate_fallback_source
```
实现前失败于 `KeyError: 'primary_candidate'`。

已跑定向 GREEN：
```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_lowering_fallback_to_legacy_is_recorded_in_plan_and_events -- --nocapture
python -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_route_decision_records_primary_candidate_fallback_source validation.tools.test_auto_migrate.AutoMigrateTests.test_normalized_artifacts_preserve_translation_fallback_source
```

边界：
- 可以说：clang-lowered typed IR 不可用后 fallback 到 legacy string translator 不再静默；translator raw artifacts、normalized plan、JSONL events 和 route decision 都能看到主候选来源。
- 可以说：这把 route metadata 往 provenance 方向做实了一步。
- 不应说：完整多候选 router、C2Rust baseline/repair 调度、LLM candidate 调度、score/hard-gate 选择器、fallback chain 优先级、或 semantic acceptance 已完成。

English mirror summary:

- Added explicit primary-candidate provenance for clang-lowering-report fallback.
- Raw translator artifacts now record `translation_source`, including selected generator and optional fallback source/reason.
- When clang-lowered typed IR is unavailable and the compatibility path uses the legacy string translator, raw and normalized JSONL events include a `translation_fallback` event.
- `auto_migrate.py` preserves `translation_source` after normalization and binds it into `route_decision.candidate_generation.primary_candidate`.
- This is provenance, not a full multi-candidate router and not semantic acceptance.

## 149. 2026-06-28 P0 post-generation candidate inventory provenance

本轮继续处理外部评价中“route 只是静态壳、没有真实候选集合”的问题。仍不一次性实现完整 L0-L4 多候选 router，而是先把后生成阶段的候选清单和选择 provenance 落到 route/profile evidence，并让 validator 能拒绝候选集合漂移和语义冒领。

核心改动：
- `validation/tools/auto_migrate.py`
  - `candidate_generation_evidence()` 现在接收 C2Rust baseline manifest 摘要，并写入：
    - `selection_policy.stage=post_generation_provenance`
    - `selection_policy.semantic_acceptance=false`
    - `selection_policy.full_router=false`
    - `selected_candidate_id`
    - `candidate_set`
  - `candidate_set` 当前包含三类后生成阶段来源：primary Rust draft、typed-IR signal、`c2rust-baseline` context。
  - `primary_candidate` 增加 `candidate_id` 和 `semantic_pass=false`，继续保留 fallback provenance。
  - `c2rust-baseline` 候选固定为 `correctness_role=candidate_context_only` 和 `semantic_pass=false`，不能作为语义通过来源。
- `validation/tools/validate_auto_translation_evidence.py`
  - 新增 candidate selection record 校验：`candidate_set` id 必须唯一，`selected_candidate_id` 必须指向集合内候选，所有 candidate 必须保持 `semantic_pass=false`。
  - `c2rust-baseline` candidate 必须保持 `candidate_context_only`，且 `candidate_generation.c2rust_baseline` 必须与 `candidate_set` 中同 id 项一致。
  - 旧 evidence 不带 `candidate_set` 时保持兼容。
- `validation/auto-translation-template/route-decision.schema.json` 与 `validation-profile.schema.json`
  - 增加 `selection_policy`、`selected_candidate_id`、`candidate_set` 和 `c2rust_baseline` 形状。
  - `candidate_generation` required 仍保持兼容策略，避免破坏旧 route/profile fixtures。
- 文档同步：
  - `README.md`
  - `docs/c2rust-migration-agent/README.md` / `.en.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.md` / `.en.md`
  - `docs/c2rust-migration-agent/future-vision-and-mvp.md` / `.en.md`
  - `docs/c2rust-migration-agent/l0-l4-routing-and-evidence-gates.md` / `.en.md`

已观察 RED：
```powershell
python -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_route_decision_records_candidate_set_and_selected_candidate
```
实现前失败于 `KeyError: 'selection_policy'`。

```powershell
python -m unittest validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_rejects_candidate_selection_id_outside_candidate_set validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_rejects_c2rust_candidate_claiming_semantic_pass
```
实现前失败于没有抛出 `SystemExit`。

边界：
- 可以说：route/profile evidence 现在有最小候选清单 provenance，并能绑定当前 primary draft 与 C2Rust baseline context。
- 可以说：validator 会拒绝 candidate id 漂移、C2Rust baseline 冒充语义来源，以及任何 candidate 自称 `semantic_pass=true`。
- 不应说：完整多候选 router、score/hard-gate 决策、C2Rust baseline/repair 实际调度、LLM candidate 调度、fallback chain 优先级、或 semantic acceptance 已完成。

English mirror summary:

- Added post-generation candidate inventory provenance to route/profile evidence.
- `candidate_set` now records the primary Rust draft, typed-IR signal, and C2Rust baseline context.
- The selected primary draft is bound through `selected_candidate_id`; C2Rust baseline remains `candidate_context_only`.
- The validator rejects candidate-set id drift, C2Rust semantic-source claims, and candidate `semantic_pass=true`.
- This remains provenance with `full_router=false`; full multi-candidate routing and semantic acceptance remain future work.

## 150. 2026-06-28 P0 repo unsafe budget and core translator CI

本轮继续 P0 “可信、可维护的翻译器核心”路线，选择核心 CI 与 repo-level unsafe budget 作为下一刀。原因：P0 要求不能只依赖 `flashDB Rust CI`，同时 unsafe budget 必须持续监控 `crates/c2r-translator`、`flashDB_rust`、`validation/l2_slices` 三个 first-party non-test Rust 范围。

核心改动：
- `.github/workflows/core-translator-validation-ci.yml`
  - 新增 core translator validation CI。
  - 跑 `cargo test --manifest-path crates/c2r-translator/Cargo.toml --quiet`。
  - 跑 `cargo test --manifest-path crates/c2r-translator/Cargo.toml --all-features --quiet`。
  - 跑核心 Python validation tests：`test_auto_migrate`、`test_validate_auto_translation_evidence`、`test_unsafe_budget`。
  - 跑 `python validation/tools/unsafe_budget.py --max-ratio 0.10`。
  - 跑 `git diff --check`。
  - 触发路径覆盖 translator、validation tools/templates、`validation/l2_slices`、competition env、unsafe ledger 和 workflow 自身。
- `validation/tools/unsafe_budget.py`
  - 新增 repo-level first-party non-test Rust unsafe scanner。
  - 默认扫描 `crates/c2r-translator/src`、`flashDB_rust/src`、`validation/l2_slices/src`。
  - 输出 JSON，包含 scopes、scanned_files、scanned_lines、unsafe findings、category counts、unsafe ratio、registration status、failed gates 和 ledger reference。
  - 默认加载 `validation/unsafe-budget-ledger.json`；当前 ledger 为空但存在，表示 0 unsafe 的登记入口也落盘。
- `validation/tools/test_unsafe_budget.py`
  - 覆盖扫描范围、忽略 tests、未登记 unsafe 失败、超过 ratio 失败、当前仓库 gate 通过，以及 core CI workflow contract。
- `validation/unsafe-budget-ledger.json`
  - 新增 repo-level unsafe registration entrypoint。
- 文档同步：
  - `README.md`
  - `docs/c2rust-migration-agent/future-vision-and-mvp.md` / `.en.md`

已观察 RED：
```powershell
python -m unittest validation.tools.test_unsafe_budget
```
最初失败于 `ImportError: cannot import name 'unsafe_budget'`。

```powershell
python -m unittest validation.tools.test_unsafe_budget.UnsafeBudgetTests.test_core_ci_runs_repo_unsafe_budget_gate
```
实现前失败于缺 `.github/workflows/core-translator-validation-ci.yml`，随后失败于 workflow 未触发 `validation/unsafe-budget-ledger.json`。

已跑定向 GREEN：
```powershell
python -m unittest validation.tools.test_unsafe_budget
python validation/tools/unsafe_budget.py --max-ratio 0.10
```
当前真实仓库 unsafe budget：`status=passed`，扫描 34 个 first-party non-test Rust 源文件、26576 行，unsafe count 为 0，ledger 已加载。

边界：
- 可以说：核心 translator + validation CI 已有正式 GitHub Actions workflow，不再只依赖 FlashDB 专用 CI。
- 可以说：repo-level unsafe budget 已有可执行 gate、测试和 ledger 入口，并接入核心 CI。
- 不应说：unsafe ledger 细粒度治理已完整；当前登记键仍是最小 path+category，后续还要补 span、替代方案、覆盖测试、source evidence 和审核状态。

English mirror summary:

- Added a core translator validation GitHub Actions workflow.
- Added a repo-level unsafe budget scanner covering `crates/c2r-translator/src`, `flashDB_rust/src`, and `validation/l2_slices/src`.
- The unsafe budget report records scope, denominator lines, findings, ratio, registration status, failed gates, and ledger reference.
- Added `validation/unsafe-budget-ledger.json` as the repo-level registration entrypoint.
- Verified the current repo has 0 first-party non-test unsafe findings across 34 Rust source files and 26576 scanned lines.

## 151. 2026-06-28 P0 C2Rust baseline candidate evidence binding

本轮继续处理外部评价中“route/candidate schema 很重，但 C2Rust baseline 只是松散 status/reason 字段”的问题。目标不是把 C2Rust 输出升级为语义证明，而是把它作为 `candidate_context_only` 时的证据引用钉牢，避免 route/profile 中的 baseline 信息与实际 manifest 或 generated output 漂移。

核心改动：
- `validation/tools/auto_migrate.py`
  - `emit_route_decision()` 现在先生成同一份 `c2rust_baseline_artifact` ref，并同时用于 `source_artifacts.c2rust_baseline` 和 `candidate_generation.c2rust_baseline.baseline_manifest`。
  - `candidate_generation_evidence()` 新增 `generated_draft_semantic_pass=false`。
  - `c2rust_baseline_candidate_binding()` 现在输出：
    - `baseline_manifest`
    - `output_ref`
    - `generated_draft_semantic_pass=false`
  - 当 baseline manifest `output` 为 generated object 时，`output_ref` 绑定 path/status/sha256；当 baseline 为 skipped/blocked 或没有 output 时，`output_ref=null`。
- `validation/tools/validate_auto_translation_evidence.py`
  - `validate_typed_ir_candidate_binding()` 把 `evidence_dir/prefix` 传给 candidate selection validator。
  - 新增 C2Rust baseline candidate binding 校验：
    - baseline manifest ref 必须有 path/status/sha256。
    - candidate 的 status/reason/correctness_role 必须与 manifest 一致。
    - generated baseline 必须校验 output_ref path/status/sha256 和实际文件 sha。
    - skipped/blocked baseline 必须保持 `output_ref=null`。
  - 新增 `require_file_ref()`，用于校验 Rust output 文件，避免用 JSON evidence helper 去读取 `.rs`。
- `validation/auto-translation-template/route-decision.schema.json`
- `validation/auto-translation-template/validation-profile.schema.json`
  - `candidateGenerationEvidence.required` 现在包含 `generated_draft_semantic_pass`。
  - `candidateSetItem` 新增可选 `baseline_manifest`、`output_ref`、`generated_draft_semantic_pass=false`。
  - 对带 `baseline_manifest` 的新格式 item 做 schema 条件约束：generated baseline 必须有 output object，skipped/blocked baseline 必须 output null。
- 测试：
  - `test_route_decision_records_candidate_set_and_selected_candidate` 现在断言 C2Rust candidate 绑定 baseline manifest 和 output_ref。
  - 新增 validator 负测覆盖 baseline status/reason drift 和 generated output_ref drift。
  - 新增 schema contract 测试覆盖 route/profile candidate set 的 C2Rust baseline ref 字段。
- 文档同步：
  - `README.md`
  - `docs/c2rust-migration-agent/README.md` / `.en.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.md` / `.en.md`
  - `docs/c2rust-migration-agent/l0-l4-routing-and-evidence-gates.md` / `.en.md`
  - `docs/c2rust-migration-agent/future-vision-and-mvp.md` / `.en.md`

已观察 RED：
```powershell
python -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_route_decision_records_candidate_set_and_selected_candidate
```
实现前失败于 `KeyError: 'generated_draft_semantic_pass'`。

```powershell
python -m unittest validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_rejects_c2rust_candidate_status_reason_drift_from_baseline_manifest validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_rejects_c2rust_generated_output_ref_drift_from_baseline_manifest
```
实现前失败于未抛出 `SystemExit`。

```powershell
python -m unittest validation.tools.test_template_schema_contracts.TemplateSchemaContractTests.test_route_and_profile_candidate_set_schema_bind_c2rust_baseline_refs
```
实现前失败于 schema 未把 `generated_draft_semantic_pass` 放入 candidate generation required，也缺 baseline/output ref 字段。

已跑相关 GREEN：
```powershell
python -m unittest validation.tools.test_auto_migrate validation.tools.test_validate_auto_translation_evidence validation.tools.test_template_schema_contracts
python -m json.tool validation/auto-translation-template/route-decision.schema.json
python -m json.tool validation/auto-translation-template/validation-profile.schema.json
```
结果：147 个 Python 相关测试通过；两份 JSON schema 可解析。

边界：
- 可以说：新生成的 route/profile C2Rust baseline candidate 已绑定 manifest 与 output ref/hash，validator 会拒绝 baseline candidate 与 manifest/output 漂移。
- 可以说：C2Rust baseline 更像真正可审计的 candidate context，而不是游离的 status/reason 摘要。
- 不应说：C2Rust baseline 已经实际调度生成候选、C2Rust 输出已经语义通过、或完整 L2 repair/router 已完成。`correctness_role` 仍必须是 `candidate_context_only`。

English mirror summary:

- Bound the route/profile C2Rust baseline candidate to the baseline manifest and optional generated output ref/hash.
- `candidate_generation` now carries `generated_draft_semantic_pass=false`; C2Rust candidate items carry `baseline_manifest`, `output_ref`, and `generated_draft_semantic_pass=false`.
- The validator rejects baseline candidate status/reason/role drift from the manifest and generated output_ref drift from the actual file hash.
- Route/profile schemas now describe the new C2Rust baseline candidate binding while keeping legacy evidence compatibility.
- This improves auditability only; C2Rust remains candidate context and is not a semantic correctness source.

## 152. 2026-06-28 P0 clang frontend fact boundary

本轮继续处理 P0 “统一 clang 前端事实”。只读子智能体确认真实 lowering 路径已经是 `CLANG_PATH` 调用 `clang -Xclang -ast-dump=json -fsyntax-only`，但 dry-run artifact、cache identity、competition profile 和部分文档仍容易让人误解为 libclang 是当前解析前端。主线选择最小切片：保留 dry-run 的诊断价值，不删除功能；把它明确标记为 diagnostic-only，并把 `LIBCLANG_PATH` 改成 ignored legacy observed metadata。

核心改动：
- `crates/c2r-translator/src/clang_frontend.rs`
  - `ClangDryRun.status` 从旧的 `ready_without_libclang` 改为 `diagnostic_only`。
  - 新增 `active_frontend`：`kind=clang_ast_dump_json`、`command="clang -Xclang -ast-dump=json -fsyntax-only"`、`required_env=["CLANG_PATH"]`、`uses_libclang=false`。
  - 新增 `claim_boundary`：`role=diagnostic_only`，不影响 manifest status，也不影响 semantic pass。
  - `ClangEnvironment` 不再暴露 `libclang_path` 作为能力字段，改为 `observed_libclang_path`；设置 `LIBCLANG_PATH` 时状态为 `ignored_for_ast_dump`。
- `crates/c2r-translator/src/artifacts.rs`
  - `*-clang-dry-run.json` 写入 `artifact_kind=clang-dry-run`、顶层 `active_frontend` 和 `claim_boundary`。
  - parse-spec 错误路径同样带 diagnostic boundary，避免 blocked artifact 暗示 libclang 前端。
- `validation/tools/auto_migrate.py`
  - `clang_lowering_identity()` 现在记录 `frontend=clang_ast_dump_json`、`command`、`requires_env=["CLANG_PATH"]`。
  - `LIBCLANG_PATH` 移到 `ignored_env_for_ast_dump.LIBCLANG_PATH`，reason 为 `ignored_for_ast_dump`。
- `config/competition-env/environment.json` 与 `validation/environment-profiles/huawei-competition-ubuntu-24.04/environment.json`
  - competition clang lane 从 `optional_env=["LIBCLANG_PATH"]` 改为 `ignored_env_for_ast_dump=["LIBCLANG_PATH"]`。
  - `future-vision-and-mvp.md` / `.en.md` 将 P0 “统一 clang 前端事实”勾选为完成。

已观察 RED：
```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-frontend clang_dry_run -- --nocapture
```
实现前失败于 `ClangDryRun` 缺少 `claim_boundary` / `active_frontend`，以及 `ClangEnvironment` 缺少 `observed_libclang_path` / `role`。

```powershell
python -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_cache_identity_records_emit_clang_lowering_report_opt_in validation.tools.test_auto_migrate.AutoMigrateTests.test_cache_identity_records_competition_clang_lane validation.tools.test_auto_migrate.AutoMigrateTests.test_real_fdb_calc_crc32_emit_clang_dry_run_opt_in_writes_temp_artifact validation.tools.test_competition_environment_profile.CompetitionEnvironmentProfileTests.test_competition_environment_profile_records_clang_lane_identity
```
实现前失败于缺 `frontend`、`artifact_kind`、`ignored_env_for_ast_dump` 等字段。

已跑 GREEN：
```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-frontend --quiet
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report --quiet
cargo test --manifest-path crates/c2r-translator/Cargo.toml --all-features --quiet
python -m unittest validation.tools.test_auto_migrate validation.tools.test_competition_environment_profile
python -m unittest validation.tools.test_auto_migrate validation.tools.test_validate_auto_translation_evidence validation.tools.test_template_schema_contracts validation.tools.test_competition_environment_profile validation.tools.test_unsafe_budget
python validation/tools/unsafe_budget.py --max-ratio 0.10
python -m json.tool config/competition-env/environment.json > $null
python -m json.tool validation/environment-profiles/huawei-competition-ubuntu-24.04/environment.json > $null
python -m json.tool docs/c2rust-migration-agent/baseline-record.json > $null
python -m json.tool validation/slice-specs/flashdb-real-fdb-calc-crc32.json > $null
git diff --check
```

结果：
- Rust all-features：67 lib/bin tests + 435 bounded_translation tests 通过。
- Python 组合：154 tests 通过（有一条 jsonschema metaschema deprecation warning，不影响结果）。
- unsafe budget：34 files / 26676 lines，0 unsafe，ratio 0.0。

边界：
- 可以说：当前 active clang frontend fact 已统一为 `CLANG_PATH` + clang AST dump JSON；dry-run 是 diagnostic-only；`LIBCLANG_PATH` 只作为 ignored metadata 记录。
- 不应说：libclang parse/lowering 已启用、`LIBCLANG_PATH` 是 optional capability、dry-run artifact 能证明 typed semantic pass、或 competition clang lane 默认开启。

English mirror summary:

- Normalized the active clang frontend contract to `CLANG_PATH` + `clang -Xclang -ast-dump=json -fsyntax-only`.
- `clang-dry-run` artifacts now carry `diagnostic_only` status, explicit claim boundary, and `active_frontend.kind=clang_ast_dump_json`.
- `LIBCLANG_PATH` is now recorded only as ignored diagnostic metadata (`ignored_env_for_ast_dump` / `observed_libclang_path`), not as an active frontend capability.
- This completes the P0 clang frontend fact-boundary item, not a real libclang parser implementation.

## 153. 2026-06-28 external review triage: oracle limits, metrics, performance

本轮处理用户贴出的外部评价，重点是判断哪些批评是当前项目已经承认的边界，哪些应该写入 `future-vision-and-mvp.md` 作为后续默认待办。

判断：
- 评价大方向有道理：C oracle 不是免费的真理机，fail-closed 会带来拒绝率和人工介入成本，Typed IR 仍窄，性能、平台/嵌入式行为、量化评估和公开案例不能靠愿景替代。
- 但部分内容已经在当前项目中覆盖：candidate 不等于 correctness source、LLM 只作候选源、C2Rust baseline 只能作 context、公开叙述不能把 native-build catalogue 当作翻译成功、unsafe budget/CI/route provenance 已经进入 P0。
- 最有增量价值的修改是把“Oracle 边界”和“量化评估”写成明确待办，而不是只在原则里泛泛说 C oracle 是 ground truth。

文档改动：
- `docs/c2rust-migration-agent/future-vision-and-mvp.md`
- `docs/c2rust-migration-agent/future-vision-and-mvp.en.md`
- `docs/c2rust-migration-agent/testing-unsafe-cache-and-milestone.md`

新增/强化的待办：
- 执行规则新增：C oracle 也有边界，必须记录 source commit、fixture、compiler/flags、target ABI、platform model、observable output contract、UB/implementation-defined、硬件/RTOS/volatile 和测试覆盖不足。
- Phase 4 新增：sanitizer / symbolic execution / property-based exploration 作为高风险 slice 的增强 oracle，不替代 fixture contract 和 C/Rust diff。
- P0 新增：强化 C oracle/UB/平台边界，每个 accepted slice 必须记录 observable outputs、fixture representativeness、compiler/flags、target ABI、endianness/word-size、sanitizer/diagnostic、UB/implementation-defined 和平台依赖建模情况。
- P1 新增：生成式能力/拒绝率 metrics artifact 和 report command，统计 generated/blocked/refused/accepted、失败原因、人工介入点、unsafe ratio、fixture case count、negative diff 覆盖和 performance-smoke 状态。
- P1 新增：把性能 smoke 前移到真实切片扩展；每个新增 L3 named slice 至少有轻量 benchmark/performance-smoke 或明确 `performance_not_claimed`。
- P1 新增：嵌入式/平台依赖边界，FlashDB/RTOS/文件系统/flash 断电恢复/volatile/硬件寄存器/线程中断交互必须有 platform contract、host simulation、target evidence 或 L4 refusal。
- P2 新增：milestone 必须发布量化评估和案例报告；没有真实项目/函数数、accepted/refused/blocked 比例、失败类别、人工介入、性能、unsafe、可复现命令、evidence hash、社区复核状态和 non-goals，就只能称研究原型/受限 MVP。
- testing/unsafe/cache 文档新增：高风险 pointer/overflow slice 可声明 sanitizer、MIRI/Kani 或 symbolic-execution profile；工具缺失必须记录 skipped/blocking reason，不能声明穷尽等价。

当前 roadmap 计数：
- Phase 1: 9/9
- Phase 2: 0/8
- Phase 3: 0/8
- Phase 4: 0/8
- P0: 7/15
- P1: 0/8
- P2: 0/6

边界：
- 可以说：这次把评价里有价值的风险显式纳入 roadmap。
- 不应说：这些新项已经实现、Oracle 完备性已解决、性能回归体系已完成、或项目已经从受限 MVP 变成通用生产工具。
