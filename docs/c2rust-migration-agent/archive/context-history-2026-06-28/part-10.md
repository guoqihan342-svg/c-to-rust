## 122. 2026-06-27 pointer graph v2 effect graph generation and validator gate

本轮继续 section 120/121 的 alias/memory-model 主线，把 `effect_graph` 从“模板字段”推进到“新生成 evidence 的真实内容和门禁”。核心目标不是扩大 C pointer 翻译语义，而是让 mutable/read pointer slice 的候选生成有可审计的 effect/alias 证据，并让缓存和 validator 能发现证据漂移。

核心改动：

- `validation/tools/auto_migrate.py`
  - 新增 `POINTER_GRAPH_SCHEMA_VERSION = 2`，新生成 pointer graph 使用 `schema_version=2`。
  - 从 `pointer_nodes[*].read_effects` / `write_effects` 生成结构化 `effect_graph.effects`。
  - 从 `alias_risks[*].pointer_nodes` 生成 alias-risk edges；`requires_noalias=true` 时写 `relationship=requires_noalias`，否则写 `may_alias`。
  - `pointer_graph.cache_invalidation_keys` 纳入 `effect_graph` 和 `effect_graph_sha256=...`。
  - `cache_identity()` 新增 `effect_graph_identity`，记录 schema version、graph hash、read/write effect counts、参与 pointer nodes、alias-sensitive 状态和最终 alias gate decision。
- `validation/tools/validate_auto_translation_evidence.py`
  - 对 `schema_version>=2` 的 alias-sensitive read/write pointer graph 条件要求 `effect_graph`。
  - 要求 effect graph 同时包含 read effects 和 write effects。
  - 要求 `summary.alias_sensitive=true` 且 `summary.alias_gate_decision` 与 alias contract decision 一致。
  - 要求每个 alias risk 都能在 effect graph 中找到对应的 `requires_noalias` 或 `may_alias` 边。
  - legacy v1 pointer graph 仍可缺省 `effect_graph`，避免破坏历史 evidence。
- 测试：
  - auto-migrate 正例覆盖 alias-sensitive read/write graph、output-only pointer write graph 和 cache identity。
  - validator 负例覆盖 v2 alias-sensitive graph 缺 `effect_graph` 必须拒绝。
  - validator 兼容例覆盖 legacy v1 read/write graph 缺 `effect_graph` 仍允许。
  - template schema contract 固定 pointer graph example 必须是 `schema_version=2`。
- 中英文文档同步：
  - `validation/pointer-graph-template/README.md`
  - `validation/pointer-graph-template/checklist.md`
  - `validation/auto-translation-template/README.md`
  - `validation/auto-translation-template/checklist.md`
  - `docs/c2rust-migration-agent/bounded-auto-translation-pipeline.md`
  - `docs/c2rust-migration-agent/bounded-auto-translation-pipeline.en.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.en.md`
  - `docs/c2rust-migration-agent/README.md`
  - `docs/c2rust-migration-agent/README.en.md`

已验证：

```powershell
python -m unittest validation.tools.test_template_schema_contracts
python -m unittest validation.tools.test_auto_migrate
python -m unittest validation.tools.test_validate_auto_translation_evidence
python -m json.tool validation/pointer-graph-template/pointer-graph.schema.json > $null
python -m json.tool validation/pointer-graph-template/pointer-graph.example.json > $null
openspec validate --all --strict
git diff --check
```

结果：

- `test_template_schema_contracts`: 4 passed。
- `test_auto_migrate`: 64 passed。
- `test_validate_auto_translation_evidence`: 69 passed。
- pointer graph schema/example JSON parse 通过。
- OpenSpec 全量 strict 校验 38 passed, 0 failed。
- `git diff --check` exit 0，仅有 Windows LF/CRLF 提示。

后续建议：

- 下一刀再考虑 struct/field access 或更宽 pointer ownership model；不要把 v2 effect graph 误当完整 alias solver。
- 如果继续加宽 mutable pointer read/write 翻译，必须先让新的 pointer effect 进入 `effect_graph_identity` 和 validator 风险边覆盖。
- `validation/tools/run_wave2_l1.py` 可后续加 competition profile guard：比赛默认环境没有 Go/CMake 时，把相关 target 标成 non-default environment required。

English mirror summary:

- Newly generated pointer graphs now use schema v2 and carry a real structured `effect_graph`.
- Alias-sensitive v2 read/write pointer graphs are validator-required to contain read effects, write effects, and alias-risk edges.
- Cache metadata now carries `effect_graph_identity`, so changed effect or alias evidence invalidates generated candidates.
- Legacy v1 pointer graph artifacts remain compatible when they omit `effect_graph`.
- Focused and full auto-migrate, validator, template schema, JSON, OpenSpec, and whitespace checks pass.

## 123. 2026-06-27 by-value record dot-field read support

本轮继续按多智能体和红测优先推进 `c2r-translator` 的通用 typed IR 覆盖，不写 FlashDB 专用代码。第 122 节建议的下一刀是 struct/field access；本节先只打通最窄的按值 record dot-field 读取，例如 `struct point p; return p.x;`，不打开 pointer `->`、字段写入或 record layout/ABI 语义。

核心改动：

- `crates/c2r-translator/src/clang_frontend.rs`
  - `ClangTypeKind` 新增 `Record { name }`，`type_from_qual_type()` 识别简单 `struct <identifier>`。
  - `ClangExprSkeleton` 新增 `Member { base, field, ty, is_arrow }`。
  - `expr_skeleton_from_ast_with_options()` 支持 clang `MemberExpr`，读取 base、field name、result type 和 `isArrow`。
  - `lower_expr()` 将 skeleton member lowering 成 typed IR `IrExpr::Member`。
  - bounded call argument guard 明确拒绝 member access call argument，避免扩大 call 子集。
- `crates/c2r-translator/src/typed_ir.rs`
  - `IrExpr` 新增 `Member`。
  - `emit_record_definitions()` 根据 record 参数和实际访问到的字段生成最小 Rust struct definition。
  - `emit_member_expr()` 只允许按值 record 变量的 dot-field read，并拒绝 `is_arrow=true`。
  - 递归验证/收集路径补齐 `Member` 分支：definite assignment、nullable pointer usage、inc/dec/assignment/comma side-effect scan、post-increment byte read scan、call callee scan、expr type 等。
  - `emit_param_type()` 可把按值 record 参数映射为 Rust PascalCase type name，例如 `struct point` -> `Point`。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增无 clang direct typed IR 测试：
    - `typed_ir_emits_record_value_field_read`
    - `typed_ir_rejects_record_arrow_field_read`
    - `typed_ir_rejects_record_param_without_modeled_field_use`
  - 新增真实 clang AST smoke：
    - `clang_ast_dump_emits_struct_field_read_when_enabled`
    - `clang_ast_dump_rejects_arrow_member_read_when_enabled`
- 中英文文档同步：
  - `docs/c2rust-migration-agent/core-translation-architecture.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.en.md`
  - `docs/c2rust-migration-agent/README.md`
  - `docs/c2rust-migration-agent/README.en.md`

已验证：

```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_emits_record_value_field_read --test bounded_translation
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_rejects_record_arrow_field_read --test bounded_translation
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_rejects_record_param_without_modeled_field_use --test bounded_translation
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features "typed-ir clang-frontend" --test bounded_translation
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --manifest-path crates/c2r-translator/Cargo.toml --features "typed-ir clang-frontend" clang_ast_dump_emits_struct_field_read_when_enabled --test bounded_translation -- --nocapture
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --manifest-path crates/c2r-translator/Cargo.toml --features "typed-ir clang-frontend" clang_ast_dump_rejects_arrow_member_read_when_enabled --test bounded_translation -- --nocapture
```

结果：

- direct typed IR 正例 1 passed，负例 2 passed。
- `bounded_translation` with `typed-ir clang-frontend`: 354 passed。
- 真实 clang AST struct field read 正例：1 passed，并通过 rustc snippet smoke。
- 真实 clang AST arrow member read 负例：1 passed。

边界：

- 可以说：按值 record 参数的 dot-field read 已能从真实 clang AST 进入 typed IR，并生成可编译 Rust candidate。
- 可以说：当前 Rust struct 是根据实际读取到的标量字段生成的最小候选结构，只用于 candidate generation。
- 不应说：已支持 C record layout/ABI 等价、无字段使用的 record 参数、`p->x`、字段赋值、compound/update 字段写、nested/anonymous record、union、bitfield、非标量字段、record local/return、struct array、address-taken record、alias write、volatile field 或 semantic acceptance。
- 后续建议：下一刀可以做 field assignment 或 pointer-aware record access，但必须先把 record layout/ownership/alias evidence 讲清楚，不能直接把 `->` lowering 成 Rust field access。

English mirror summary:

- Added narrow by-value record dot-field read support through clang skeleton, typed IR, and the generic emitter.
- `struct point p; return p.x;` now emits a minimal Rust `Point` struct plus `return p.x;` as a candidate.
- Pointer member access `p->x`, record params with no modeled field use, field writes, record layout/ABI claims, unions/bitfields, volatile fields, and semantic acceptance still fail closed.
- Direct typed IR, full bounded translation, and real clang AST positive/negative smoke tests pass.

## 124. 2026-06-28 by-value record dot-field assignment support

本轮继续扩 generic typed IR emitter 的通用 record 能力，不写 FlashDB/crc32 特例。目标是把上一节的按值 record dot-field read 往前推进一小步：支持简单 `p.x = value; return p.x;` 这种 by-value record 字段赋值 candidate，但仍不打开 pointer `->`、alias-sensitive 字段写、compound/update 字段写或 record layout/ABI 语义。

核心改动：

- `crates/c2r-translator/src/typed_ir.rs`
  - `emit_assignment_target()` 新增 `IrExpr::Member` 赋值目标分支，复用 `emit_member_expr()` 的窄化 guard。
  - `validate_definite_assignment_target()` 接受 member 赋值目标并验证 base 表达式。
  - `assigned_var_name_from_target()` 识别 member base 变量，使 `p.x = value` 能把按值 record 参数发射为 `mut p: Point`。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 direct typed IR 正测：`typed_ir_emits_record_value_field_assignment`。
  - 新增 direct typed IR 负测：`typed_ir_rejects_record_arrow_field_assignment`。
  - 新增真实 clang AST smoke：`clang_ast_dump_emits_struct_field_assignment_when_enabled`。
- 中英文文档同步：
  - `docs/c2rust-migration-agent/core-translation-architecture.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.en.md`
  - `docs/c2rust-migration-agent/README.md`
  - `docs/c2rust-migration-agent/README.en.md`
  - `docs/c2rust-migration-agent/COVERAGE.md`
  - `docs/c2rust-migration-agent/COVERAGE.en.md`
  - `docs/c2rust-migration-agent/future-vision-and-mvp.md`
  - `docs/c2rust-migration-agent/future-vision-and-mvp.en.md`

已验证：

```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_emits_record_value_field_assignment --test bounded_translation
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_rejects_record_arrow_field_assignment --test bounded_translation
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --manifest-path crates/c2r-translator/Cargo.toml --features "typed-ir clang-frontend" clang_ast_dump_emits_struct_field_assignment_when_enabled --test bounded_translation -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir record --test bounded_translation
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features "typed-ir clang-frontend" --test bounded_translation
cargo test --manifest-path crates/c2r-translator/Cargo.toml --all-features
openspec validate --all --strict
git diff --check
```

结果：

- direct typed IR field assignment 正例：1 passed。
- direct typed IR arrow field assignment 负例：1 passed。
- 真实 clang AST struct field assignment 正例：1 passed，并通过 rustc snippet smoke。
- `record` filter：12 passed。
- `bounded_translation` with `typed-ir clang-frontend`：357 passed。
- `--all-features`：52 个 lib tests + 358 个 bounded tests + doc tests 通过。
- OpenSpec 全量 strict：38 passed, 0 failed。
- `git diff --check` exit 0，仅有 Windows LF/CRLF warning。

边界：

- 可以说：按值 record 参数的 dot-field read 和简单 dot-field assignment 已能从真实 clang AST 进入 typed IR，并生成可编译 Rust candidate。
- 可以说：`p.x = value` 会把 Rust 参数标为 `mut p: Point`，并只复用最小 Rust struct candidate shape。
- 不应说：已支持 C record layout/ABI 等价、无字段使用的 record 参数、`p->x`、compound/update 字段写、pointer/alias-sensitive 字段写、nested/anonymous record、union、bitfield、非标量字段、record local/return、struct array、address-taken record、alias write、volatile field 或 semantic acceptance。
- 后续建议：下一刀优先做 record local/return 最小模型或 pointer-aware record access 设计；后者必须先绑定 alias/ownership/effect evidence，不能直接把 `->` 翻译成 Rust field access。

English mirror summary:

- Added narrow by-value record dot-field assignment support to the generic typed IR emitter.
- `struct point p; p.x = value; return p.x;` now emits a minimal Rust `Point` struct, `mut p: Point`, `p.x = value;`, and `return p.x;` as a candidate.
- Pointer member access `p->x`, compound/update field writes, pointer/alias-sensitive field writes, record layout/ABI claims, record locals/returns, unions/bitfields, volatile fields, and semantic acceptance still fail closed.
- Direct typed IR, real clang AST smoke, full bounded translation, all-features tests, OpenSpec, and whitespace checks pass.

## 125. 2026-06-28 initialized by-value record local copy support

本轮继续按多智能体推进 P1 record 子集。只读代理共同结论：不要直接实现 `p->x`，因为它需要 pointer/record ownership、non-null/lifetime/alias/effect evidence；也不要直接实现 whole-record return，因为当前 Rust record 仍是从实际访问到的标量字段生成的最小 candidate shape，不是完整 C layout/ABI proof。本节只收敛纯 by-value 的 record local copy：`struct point q = p; q = r; return q.x;`。

核心改动：

- `crates/c2r-translator/src/typed_ir.rs`
  - 新增内部 `emit_value_type()`，允许当前 value-position 在标量之外识别 by-value record type name。
  - `emit_stmt(Decl)` 支持带 initializer 的 record local declaration，发射 `let q: Point = p;`；无 initializer 的 record local 明确 fail closed。
  - `emit_expr(Var)` 允许 record value variable 用作本地 copy initializer / assignment RHS。
  - `validate_expr_matches_type()` 改成用 value type 校验标量和 record type identity，但仍不打开 pointer/array/unsupported aggregate。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 direct typed IR 正测：
    - `typed_ir_emits_record_local_copy_field_read`
    - `typed_ir_emits_record_local_copy_with_equivalent_record_spelling`
    - `typed_ir_emits_record_local_copy_field_assignment`
    - `typed_ir_emits_record_local_assignment_value_copy`
  - 新增 direct typed IR 负测：
    - `typed_ir_rejects_uninitialized_record_local_decl`
    - `typed_ir_rejects_record_return_value_without_complete_field_model`
    - `typed_ir_rejects_record_value_direct_call_arguments`
  - 新增真实 clang AST smoke：
    - `clang_ast_dump_emits_struct_local_copy_field_read_when_enabled`
    - `clang_ast_dump_emits_struct_local_assignment_value_copy_when_enabled`
    - `clang_ast_dump_rejects_struct_return_value_when_enabled`
- 中英文文档同步：
  - `docs/c2rust-migration-agent/core-translation-architecture.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.en.md`
  - `docs/c2rust-migration-agent/README.md`
  - `docs/c2rust-migration-agent/README.en.md`
  - `docs/c2rust-migration-agent/COVERAGE.md`
  - `docs/c2rust-migration-agent/COVERAGE.en.md`
  - `docs/c2rust-migration-agent/future-vision-and-mvp.md`
  - `docs/c2rust-migration-agent/future-vision-and-mvp.en.md`

当前已验证：

```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_emits_record_local_copy_field_read --test bounded_translation
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir record_local --test bounded_translation
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir record --test bounded_translation
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --manifest-path crates/c2r-translator/Cargo.toml --features "typed-ir clang-frontend" clang_ast_dump_emits_struct_local_copy_field_read_when_enabled --test bounded_translation -- --nocapture
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --manifest-path crates/c2r-translator/Cargo.toml --features "typed-ir clang-frontend" clang_ast_dump_rejects_struct_return_value_when_enabled --test bounded_translation -- --nocapture
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --manifest-path crates/c2r-translator/Cargo.toml --features "typed-ir clang-frontend" clang_ast_dump_emits_struct_local_assignment_value_copy_when_enabled --test bounded_translation -- --nocapture
```

结果：

- `typed_ir_emits_record_local_copy_field_read` 先红后绿；初始失败为 `stmt[0].decl q has record type point is unsupported`。
- `typed_ir_emits_record_local_copy_with_equivalent_record_spelling` 先红后绿；初始失败为 `type Point does not match expected type Point`，修复为 value-type compatibility 而不是完整 `IrType` 结构相等。
- `record_local` filter：5 passed。
- `record` filter：17 passed。
- `typed_ir_rejects_record_value_direct_call_arguments`：1 passed，固定 record value direct call argument 继续 fail closed。
- 真实 clang AST local copy read 正例：1 passed，并通过 rustc snippet smoke。
- 真实 clang AST whole-record return 负例：1 passed。
- 真实 clang AST local assignment copy 正例：1 passed，并通过 rustc snippet smoke。

边界：

- 可以说：已初始化本地 record copy 和本地 record copy assignment 在后续只访问已建模标量字段时，可作为 `GenericTypedIr` candidate 生成可编译 Rust。
- 不应说：已支持 whole-record return、完整 record local model、record layout/ABI、无初始化 record local、compound literal、designated initializer、`p->x`、record pointer/alias-sensitive field access、address-taken record、volatile/packed/bitfield/union/nested/anonymous record、非标量字段、record call arguments 或 semantic acceptance。
- 后续建议：下一刀如果继续 record，应先补 whole-record return 的完整 field/layout inventory 证据；如果转向 `p->x`，必须先补 pointer graph v2 示例/校验、record field/layout evidence、non-null/lifetime/alias/effect preconditions 和 fail-closed 测试矩阵。

English mirror summary:

- Added initialized by-value record local copy support to the generic typed IR emitter.
- `struct point q = p; q = r; return q.x;` now emits a minimal Rust `Point` struct plus `let mut q: Point = p; q = r; return q.x;` as a candidate.
- Whole-record return, uninitialized record locals, `p->x`, pointer/alias-sensitive field access, record layout/ABI claims, compound literals, designated initializers, unions/bitfields/volatile fields, and semantic acceptance still fail closed.
- Verification now passes after the value-type compatibility fix: `cargo test --manifest-path crates/c2r-translator/Cargo.toml --features "typed-ir clang-frontend" --test bounded_translation` passed 367/367 tests; `cargo test --manifest-path crates/c2r-translator/Cargo.toml --all-features` passed 52 lib tests, 368 bounded tests, and doc tests; `openspec validate --all --strict` passed 38/38 items; `git diff --check` reported only Windows LF-to-CRLF warnings.

## 126. 2026-06-28 complete record field inventory and whole-record return candidates

本轮继续按多智能体推进 P1 record 子集。两个只读代理结论一致：`p->x` 不应直接放开，因为它需要 readonly struct pointer、non-null/lifetime/alignment、pointer graph read effect、alias/effect gate 和 record ownership 证据；whole-record return 也不能只改 emitter，必须先有完整字段清单。本节完成的切口是：从真实 clang AST 的唯一具名完整 `RecordDecl` / `FieldDecl` 提取直接标量字段清单，并仅在该清单存在时允许 by-value whole-record return candidate，例如 `struct point { int x; int y; }; struct point identity_point(struct point p) { return p; }`。复审后又收紧了两个边界：同名 tag 不复用字段清单，自引用/指针字段不会递归展开，而是 fail closed。

核心改动：

- `crates/c2r-translator/src/typed_ir.rs`
  - 新增 `IrRecordField`，`IrTypeKind::Record` 现在可携带 `fields: Option<Vec<IrRecordField>>`。
  - `emit_record_definitions()` 会把 return type 中的完整字段清单并入 Rust struct 定义；字段访问路径仍可沿用实际访问字段的最小候选形状。record 参数本身不会单独打开完整 struct 定义。
  - `emit_return_type()` 只在 record type 带完整字段清单时允许发射 `-> Point`；无字段清单的 whole-record return 继续 fail closed。
  - record 字段仍必须由 `emit_scalar_type()` 支持；非标量字段继续 fail closed。
- `crates/c2r-translator/src/clang_frontend.rs`
  - 真实 clang AST dump 路径新增 `record_inventory_from_ast()`，从唯一具名、完整、非 implicit、非 packed 的 `struct RecordDecl` 中收集直接标量 `FieldDecl`。
  - bitfield、volatile field、匿名/嵌套 record、同名 tag、self-pointer field、unsupported/non-scalar field type 不进入完整字段清单。
  - lowering 完成后把字段清单 attach 到 `IrFunction` 的 return type、decl、expr 等直接类型位置；不沿 pointer/array/字段类型递归展开，避免自引用 record 在 emitter 前栈溢出。
- `crates/c2r-translator/src/lib.rs`
  - 更新 `IrTypeKind::Record` 匹配和测试 helper，兼容新增 `fields` 字段。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 direct typed IR 正测：
    - `typed_ir_emits_record_return_value_with_complete_field_inventory`
  - 新增 direct typed IR 负测：
    - `typed_ir_rejects_record_return_value_with_non_scalar_field_inventory`
    - `typed_ir_rejects_record_return_value_with_mismatched_field_inventory`
  - 将真实 clang AST whole-record return smoke 从拒绝改成正测：
    - `clang_ast_dump_emits_struct_return_value_when_enabled`
  - 新增真实 clang AST fail-closed smoke：
    - `clang_ast_dump_rejects_struct_return_value_with_bitfield_when_enabled`
    - `clang_ast_dump_rejects_struct_return_value_with_volatile_field_when_enabled`
    - `clang_ast_dump_rejects_struct_return_value_with_packed_record_when_enabled`
    - `clang_ast_dump_rejects_struct_return_value_with_packed_field_when_enabled`
    - `clang_ast_dump_rejects_struct_return_value_with_duplicate_tag_name_when_enabled`
    - `clang_ast_dump_rejects_struct_return_value_with_self_pointer_field_when_enabled`
- 中英文文档同步：
  - `docs/c2rust-migration-agent/COVERAGE.md`
  - `docs/c2rust-migration-agent/COVERAGE.en.md`
  - `docs/c2rust-migration-agent/README.md`
  - `docs/c2rust-migration-agent/README.en.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.en.md`
  - `docs/c2rust-migration-agent/future-vision-and-mvp.md`
  - `docs/c2rust-migration-agent/future-vision-and-mvp.en.md`

当前已验证：

```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_emits_record_return_value_with_complete_field_inventory --test bounded_translation
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --manifest-path crates/c2r-translator/Cargo.toml --features "typed-ir clang-frontend" clang_ast_dump_emits_struct_return_value_when_enabled --test bounded_translation -- --nocapture
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --manifest-path crates/c2r-translator/Cargo.toml --features "typed-ir clang-frontend" struct_return --test bounded_translation -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir record --test bounded_translation
cargo test --manifest-path crates/c2r-translator/Cargo.toml --all-features
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --manifest-path crates/c2r-translator/Cargo.toml --features "typed-ir clang-frontend" --test bounded_translation
```

结果：

- `typed_ir_emits_record_return_value_with_complete_field_inventory` 通过，生成 `pub struct Point { pub x: i32, pub y: u32 }` 和 `pub fn identity_point(p: Point) -> Point`。
- 真实 clang AST `identity_point()` 正例通过，并证明未访问字段 `y` 也来自完整 `RecordDecl` / `FieldDecl` 清单。
- `struct_return` filter：7 passed。
- `record` filter：22 passed。
- `--all-features`：52 个 lib tests + 377 个 bounded tests + doc tests 通过。
- `typed-ir clang-frontend` full bounded translation：376 passed；本次设置了 `C2R_RUN_CLANG_AST_TESTS=1` 和 `CLANG_PATH=C:\Program Files\LLVM\bin\clang.exe`，真实 clang smoke 实际执行。

边界：

- 可以说：唯一具名完整直接标量字段清单存在时，by-value whole-record return 可作为 `GenericTypedIr` candidate 生成可编译 Rust。
- 不应说：已支持 C record layout/ABI 等价、semantic acceptance、`p->x`、record pointer/alias-sensitive access、compound/update 字段写、record pointer writes、同名 tag、self-pointer field、bitfield、volatile/packed record、union、匿名/嵌套 record、非标量字段、struct array 或 address-taken record。
- 后续建议：下一刀如果继续 record，应优先做 pointer-aware readonly `const struct T *p -> p->scalar_field` 的 evidence 契约和红测；必须先补 pointer graph read effect、non-null/lifetime/alignment preconditions、alias/effect gate 和 fail-closed matrix。

English mirror summary:

- Added unique named complete direct scalar record field inventory to typed IR and real clang AST lowering.
- Whole-record by-value return is now a candidate only when that unique complete scalar inventory exists.
- Duplicate tags, self-pointer fields, bitfields, volatile fields, packed records, non-scalar fields, `p->x`, pointer/alias-sensitive record access, layout/ABI claims, and semantic acceptance still fail closed.
- Verification: record filter, struct-return regression tests, `--all-features`, and full real-clang bounded translation pass. `openspec validate --all --strict` passed 38/38. `git diff --check` reported only Windows LF-to-CRLF warnings.

## 127. 2026-06-28 by-value record field compound assignment candidates

本轮继续按多智能体推进 P1 record/compound-assignment 子集。只读代理结论一致：`p->x` 仍不应直接放开，因为缺少 readonly struct pointer 的 non-null/lifetime/alignment、pointer graph read effect、alias/effect gate 和 record ownership 证据；更安全的下一小步是按值 record dot-field compound assignment。完成切口是：`struct point { int x; int y; }; int add_point_x(struct point p, int value) { p.x += value; return p.x; }` 现在可从真实 clang AST lowering 到 typed IR，并由 generic emitter 生成可编译 Rust candidate：

```rust
pub fn add_point_x(mut p: Point, value: i32) -> i32 {
    p.x = (p.x + value);
    return p.x;
}
```

核心改动：

- `crates/c2r-translator/src/clang_frontend.rs`
  - 新增 `compound_assignment_target_type()`，把 compound-assignment target guard 从“只能 `DeclRef`”扩展为“`DeclRef` 或 by-value record dot-field target”。
  - 新增 record-field compound RHS guard：只有简单整数变量、整数字面量和整数 cast 包裹的简单值可以作为 RHS；`value + 1`、call、member/index、非整数 RHS 都 fail closed。
  - by-value record dot-field target 要求 `Member { is_arrow: false }`，且 base 必须是直接 `DeclRef` record 变量。
  - `p->field` 明确以 pointer/record ownership evidence 缺失为由 fail closed；`*p += y`、`a[i] += y`、`(*p).x += y`、非直接 record 变量 base 仍 fail closed。
  - `lower_compound_assign_stmt()` 不再手写 `IrExpr::Var` target，而是复用 `lower_expr(target)`，因此 `p.x += value` lowering 成 `IrStmt::Assign { target: Member(p.x), value: Binary(Member(p.x), Add, value) }`。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 direct typed IR shape 测试：`typed_ir_emits_record_value_field_compound_assignment_shape`。
  - 新增 clang skeleton lowering 测试：
    - `clang_lowering_skeleton_maps_record_field_compound_assignment`
    - `clang_lowering_skeleton_maps_record_field_compound_assignment_literal_and_cast_rhs`
  - 新增 clang skeleton fail-closed 测试：
    - `clang_lowering_skeleton_rejects_record_field_compound_assignment_complex_rhs`
    - `clang_lowering_skeleton_rejects_record_field_compound_assignment_non_integer_rhs`
    - `clang_lowering_skeleton_rejects_record_field_compound_assignment_call_rhs`
    - `clang_lowering_skeleton_rejects_record_field_compound_assignment_member_rhs`
    - `clang_lowering_skeleton_rejects_record_field_compound_assignment_index_rhs`
    - `clang_lowering_skeleton_rejects_record_field_compound_assignment_arrow_target`
    - `clang_lowering_skeleton_rejects_record_field_compound_assignment_nested_base`
    - `clang_lowering_skeleton_rejects_record_field_compound_assignment_deref_target`
    - `clang_lowering_skeleton_rejects_record_field_compound_assignment_index_target`
  - 新增真实 clang AST smoke：`clang_ast_dump_emits_struct_field_compound_assignment_when_enabled`。
  - 新增真实 clang AST fail-closed smoke：`clang_ast_dump_rejects_struct_field_compound_assignment_complex_rhs_when_enabled`。
- 中英文文档同步：
  - `docs/c2rust-migration-agent/COVERAGE.md`
  - `docs/c2rust-migration-agent/COVERAGE.en.md`
  - `docs/c2rust-migration-agent/README.md`
  - `docs/c2rust-migration-agent/README.en.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.en.md`
  - `docs/c2rust-migration-agent/future-vision-and-mvp.md`
  - `docs/c2rust-migration-agent/future-vision-and-mvp.en.md`

当前已验证：

```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --all-features clang_lowering_skeleton_maps_record_field_compound_assignment -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --all-features typed_ir_emits_record_value_field_compound_assignment_shape -- --nocapture
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --manifest-path crates/c2r-translator/Cargo.toml --all-features clang_ast_dump_emits_struct_field_compound_assignment_when_enabled -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --all-features compound_assignment --test bounded_translation -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --all-features record --test bounded_translation -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --all-features record_field_compound_assignment --test bounded_translation -- --nocapture
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --manifest-path crates/c2r-translator/Cargo.toml --all-features clang_ast_dump_rejects_struct_field_compound_assignment_complex_rhs_when_enabled --test bounded_translation -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --all-features
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --manifest-path crates/c2r-translator/Cargo.toml --features "typed-ir clang-frontend" --test bounded_translation -- --nocapture
openspec validate --all --strict
git diff --check
```

结果：

- TDD 红测先失败于 `unsupported_compound_assignment_target: compound assignment target must be a simple variable`，实现后通过。
- 复审后补的复杂 RHS 红测先证明 `p.x += value + 1` 会被错误 lowering 成 IR；补 RHS guard 后通过。
- `compound_assignment` filter：22 passed。
- `record` filter：41 passed。
- `record_field_compound_assignment` filter：11 passed。
- `--all-features`：52 个 lib tests + 391 个 bounded tests + doc tests 通过。
- 显式真实 clang bounded translation：390 passed，`C2R_RUN_CLANG_AST_TESTS=1` 且 `CLANG_PATH=C:\Program Files\LLVM\bin\clang.exe`。
- `openspec validate --all --strict`：38/38 passed。
- `git diff --check`：仅报告 Windows LF-to-CRLF warnings。

边界：

- 可以说：standalone statement 中 RHS 为简单整数变量/字面量/整数 cast 的 by-value record dot-field compound assignment（例如 `p.x += value`）现在可作为 `GenericTypedIr` candidate 生成可编译 Rust。
- 不应说：已支持 `p->x`、`p->x += value`、字段 update/inc-dec（`p.x++`）、record field compound assignment 复杂 RHS（如 `p.x += value + 1` / call / member/index RHS）、指针/alias-sensitive 字段写、非直接 record 变量 base、record layout/ABI 等价、semantic acceptance、volatile/hardware register 或完整 C compound-assignment 语义。
- 后续建议：如果继续 record，下一刀仍应优先补 pointer-aware readonly `const struct T *p -> p->scalar_field` evidence 契约和红测；如果继续字段写，优先设计 `p.x++` / update field write 的 statement-side-effect 边界，不要把 value-position inc/dec 混进来。

English mirror summary:

- Added by-value record dot-field compound-assignment candidate generation for standalone statements such as `p.x += value`, with RHS limited to a simple integer variable, literal, or integer cast.
- Clang lowering now accepts compound-assignment targets that are either simple scalar variables or direct by-value record dot fields; arrow members, deref/index targets, and non-direct record bases still fail closed.
- Record field compound-assignment complex RHS, including `value + 1`, calls, member/index RHS, and non-integer RHS, fails closed.
- The generic typed IR shape emits `p.x = (p.x + value);` and marks the by-value record parameter mutable.
- `p->x`, pointer/alias-sensitive field writes, field update/inc-dec, C record layout/ABI claims, and semantic acceptance still fail closed.
- Verification: targeted TDD red/green test, compound/record filters, `--all-features`, full real-clang bounded translation, OpenSpec strict validation, and `git diff --check` all pass, with only Windows LF-to-CRLF warnings from `git diff --check`.

## 128. 2026-06-28 by-value record dot-field inc/dec statements

本轮继续按多智能体推进 P1 record 字段写入子集，不写 FlashDB/crc32 特例。只读代理结论一致：`p->x` 仍需要 pointer/record ownership、non-null/lifetime/alignment、alias/effect 和 pointer graph read/write evidence；value-position `p.x++` 需要表达式旧值/新值语义和副作用排序证明；更安全的切口是 standalone statement 中表达式值被丢弃的 direct by-value record dot-field inc/dec。完成切口是：`struct point { int x; int y; }; int bump_point_x(struct point p) { p.x++; ++p.x; p.x--; --p.x; return p.x; }` 现在可从真实 clang AST lowering 到 typed IR，并由 generic emitter 生成可编译 Rust candidate：

```rust
pub fn bump_point_x(mut p: Point) -> i32 {
    p.x = (p.x + 1i32);
    p.x = (p.x + 1i32);
    p.x = (p.x - 1i32);
    p.x = (p.x - 1i32);
    return p.x;
}
```

核心改动：

- `crates/c2r-translator/src/clang_frontend.rs`
  - `inc_dec_stmt_skeleton_from_ast()` 不再只接受 simple `DeclRef` target，而是复用新 helper `inc_dec_assignment_target_type()` 判断 inc/dec assignment target。
  - helper 接受 simple integer variable 和 standalone statement 中的 direct by-value record dot-field integer target。
  - `Member { is_arrow: true }` 以缺少 pointer/record ownership evidence 为由 fail closed。
  - dot-field target 要求 base 是直接 `DeclRef` record 变量；嵌套 base、非 record base、deref/index/复杂 target 继续 fail closed。
  - `ForStmt` step 仍只接受 simple scalar variable inc/dec；record-field inc/dec step 显式 fail closed，避免把 loop step 顺序和字段副作用边界混入本切口。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增真实 clang AST 正测：`clang_ast_dump_emits_record_field_inc_dec_statements_when_enabled`。
  - 新增真实 clang AST fail-closed smoke：
    - `clang_ast_dump_rejects_arrow_record_field_inc_dec_statement_when_enabled`
    - `clang_ast_dump_rejects_record_field_inc_dec_return_value_when_enabled`
    - `clang_ast_dump_rejects_record_field_inc_dec_for_step_when_enabled`
    - `clang_ast_dump_rejects_nested_record_field_inc_dec_statement_when_enabled`
  - 正测断言 4 个字段 assignment 加 return，并验证生成 Rust snippet 可编译。
- `crates/c2r-translator/src/clang_frontend.rs` 单元测试新增：
  - `stmt_skeleton_from_ast_accepts_record_field_inc_dec_statement_as_assignment`
  - `stmt_skeleton_from_ast_rejects_record_field_inc_dec_arrow_target`
  - `for_step_stmt_skeleton_from_ast_rejects_record_field_inc_dec_step`
  - `stmt_skeleton_from_ast_rejects_record_field_inc_dec_nested_base`
- 中英文文档同步：
  - `docs/c2rust-migration-agent/COVERAGE.md`
  - `docs/c2rust-migration-agent/COVERAGE.en.md`
  - `docs/c2rust-migration-agent/README.md`
  - `docs/c2rust-migration-agent/README.en.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.md`
  - `docs/c2rust-migration-agent/core-translation-architecture.en.md`
  - `docs/c2rust-migration-agent/future-vision-and-mvp.md`
  - `docs/c2rust-migration-agent/future-vision-and-mvp.en.md`

当前已验证：

```powershell
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --manifest-path crates/c2r-translator/Cargo.toml --all-features record_field_inc_dec -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --all-features
$env:C2R_RUN_CLANG_AST_TESTS='1'; $env:CLANG_PATH='C:\Program Files\LLVM\bin\clang.exe'; cargo test --manifest-path crates/c2r-translator/Cargo.toml --features "typed-ir clang-frontend" --test bounded_translation -- --nocapture
openspec validate --all --strict
rustfmt --check --edition 2021 crates/c2r-translator/src/clang_frontend.rs crates/c2r-translator/tests/bounded_translation.rs
git diff --check
```

结果：

- TDD 红测先失败于 `statement inc/dec target must be a simple variable`，实现后通过。
- `record_field_inc_dec` filter：4 个 lib 单元测试 + 5 个真实 clang bounded tests 通过。
- `--all-features`：56 个 lib tests + 396 个 bounded tests + doc tests 通过。
- 显式真实 clang bounded translation：395 passed，`C2R_RUN_CLANG_AST_TESTS=1` 且 `CLANG_PATH=C:\Program Files\LLVM\bin\clang.exe`。
- `openspec validate --all --strict`：38/38 passed。
- 定向 `rustfmt --check`：exit 0。
- `git diff --check`：exit 0，仅报告 Windows LF-to-CRLF warnings。

边界：

- 可以说：standalone statement 中的 direct by-value record dot-field integer `p.x++` / `++p.x` / `p.x--` / `--p.x` 现在可作为 `GenericTypedIr` candidate 生成可编译 Rust。
- 不应说：已支持 value-position `p.x++`、return/call/condition 中的字段 inc/dec、`ForStmt` step 中 record-field inc/dec、`p->x++`、nested/complex base、pointer/alias-sensitive 字段写、record layout/ABI 等价、volatile/hardware register 或完整 C inc/dec 表达式语义。
- 后续建议：如果继续 record，下一刀更适合 pointer-aware readonly `const struct T *p -> p->scalar_field` evidence 契约和红测；如果继续字段更新，需要先设计 value-position inc/dec 旧值语义、副作用排序和 alias gate，而不是直接泛化 helper。

English mirror summary:

- Added by-value record dot-field inc/dec candidate generation for standalone value-discarded statements such as `p.x++`, `++p.x`, `p.x--`, and `--p.x`.
- Clang statement lowering now accepts simple integer variables and direct by-value record dot-field integer targets; arrow members, nested bases, complex targets, and record-field `ForStmt` steps still fail closed.
- Real clang smoke covers positive statement lowering, arrow-member rejection, value-position return rejection, record-field `ForStmt` step rejection, and nested-base rejection.
- This remains candidate generation only. `p->x++`, value-position field inc/dec, pointer/alias-sensitive field writes, C record layout/ABI claims, and semantic acceptance still fail closed.

## 129. 2026-06-28 P0 lib.rs public model split

本轮继续按 P0 “拆分 `crates/c2r-translator/src/lib.rs`”推进维护性工作，不新增翻译语法，也不改变公开行为。两个只读子智能体先复核了 `lib.rs` 职责边界和外部 API：最小风险第一刀是把纯公开 DTO/schema 搬出 `lib.rs`，保留 crate root re-export；暂不碰 parser、emitter、artifact writer 或 `clang-lowering-report` 逻辑，因为这些区域互调密集、feature gate 交叉更多。

核心改动：

- 新增 `crates/c2r-translator/src/model.rs`：
  - 承载 `BuildProfile`、`SliceSpec`、`SourceFileRef`、`SourceSpanRef`、`TranslationResult`、`TranslationError`、`TypeMapEvidence`、`TypeMapping`、`TypeUncertainty`、`CfgEvidence`、`CfgFunction`、`CfgBlock`、`PointerGraphEvidence`、`PointerNode`、`PointerEdge`、`TranslationPlan`、`CallExpressionEvidence`、`ArtifactManifest`。
  - 原有 `serde` derive、`Default` derive 和 `#[serde(default)]` 字段保持不变，避免破坏 JSON schema/CLI 输入契约。
- `crates/c2r-translator/src/lib.rs`：
  - 新增私有 `mod model;`。
  - 用显式 `pub use model::{...};` 保持原 root API，例如 `c2r_translator::SliceSpec`、`c2r_translator::BuildProfile`、`c2r_translator::ArtifactManifest`。
  - `BTreeMap` 改成只在 `clang-lowering-report` feature 下导入，避免默认 feature warning。
  - 运行 rustfmt 后顺手收敛了两个既有测试断言格式差异；行为不变。

当前已验证：

```powershell
cargo fmt --manifest-path crates/c2r-translator/Cargo.toml -- --check
cargo check --manifest-path crates/c2r-translator/Cargo.toml --all-targets --all-features
cargo test --manifest-path crates/c2r-translator/Cargo.toml
cargo test --manifest-path crates/c2r-translator/Cargo.toml --all-features
openspec validate --all --strict
```

结果：

- `cargo fmt --check`：exit 0。
- `cargo check --all-targets --all-features`：exit 0。
- 默认 feature 测试：35 个 bounded tests 通过。
- `--all-features`：56 个 lib tests + 396 个 bounded tests + doc tests 通过。
- `openspec validate --all --strict`：38/38 passed。
- `lib.rs` 当前约 4066 行；公开 model schema 被移到 149 行的 `model.rs`。这只是 P0 拆分第一刀，尚未完成 P0 对 CLI/manifest、旧字符串 translator、typed IR route、artifact 写入、unsafe/metadata 统计等责任的后续拆分要求。

边界：

- 可以说：公开 DTO/schema 已从 `lib.rs` 拆出，crate root API 和 serde schema 保持兼容。
- 不应说：`lib.rs` 拆分 P0 已完成、translator 架构已模块化完成、或新增了任何 C 语法翻译能力。
- 后续建议：下一刀优先拆 artifact writer / translation event JSONL / clang dry-run artifact writer 这类 IO 边界；再逐步拆 parser、legacy string translator、evidence builder 和 emitter。每一刀都要保持 root API、feature matrix 和现有测试通过。

English mirror summary:

- Started the P0 `lib.rs` split with a behavior-preserving public model extraction.
- Public DTO/schema types moved into private `model.rs`, while root-level re-exports keep `c2r_translator::SliceSpec`, `BuildProfile`, `TranslationResult`, `ArtifactManifest`, and related types compatible.
- Serde derives/default fields were preserved; no translation behavior or C syntax coverage changed.
- This is only the first P0 split step. CLI/manifest, legacy string translator, typed IR route, artifact writing, unsafe/metadata statistics, parser, evidence builder, and emitter responsibilities still need later splits.

## 130. 2026-06-28 P0 artifact/IO leaf helper split

本轮继续按 P0 “拆分 `crates/c2r-translator/src/lib.rs`”推进维护性工作，仍然不新增翻译语法、不改变 public API、不改变 artifact 文件名、manifest status 或 feature gate 语义。两个只读子智能体并行复核后结论一致：`write_translation_artifacts()` 是 public orchestration，仍然绑定 `translate_slice()`、可选 clang-lowering 翻译路径、artifact 顺序和 `ArtifactManifest` 状态，第一刀不应整体搬迁；更稳的切口是先拆纯 leaf helper。

核心改动：

- 新增 `crates/c2r-translator/src/artifacts.rs`：
  - 承载 `write_json_file()`、`write_text_file()`、`translation_events_jsonl()`。
  - 三个 helper 都是 `pub(crate)`，模块本身保持私有 `mod artifacts;`，不新增外部 API。
  - `translation_events_jsonl()` 保持既有事件语义：先写 `translation_started`；有错误时写每个 `translation_blocked`；无错误时写 `translation_generated`。
- `crates/c2r-translator/src/lib.rs`：
  - 通过 `use artifacts::{translation_events_jsonl, write_json_file, write_text_file};` 继续调用 leaf helper。
  - `write_translation_artifacts()`、`write_clang_dry_run_artifact()`、`write_clang_lowering_report_artifact()` 暂留原处，避免把 IO 拆分和 clang/typed-IR 语义路径混在同一提交。
  - `PathBuf` 改成仅在 `clang-frontend` 或 `clang-lowering-report` feature 下导入，默认 feature 不再产生拆分后的 unused import warning。
- 新增单元测试 `artifact_tests::translation_events_jsonl_records_blocked_errors`：
  - 红测先失败于 `crate::artifacts` 不存在。
  - 实现后验证 blocked JSONL 会包含 `translation_started` + `translation_blocked`，且不会误写 `translation_generated`。
- 同步中英文待办：
  - `docs/c2rust-migration-agent/future-vision-and-mvp.md`
  - `docs/c2rust-migration-agent/future-vision-and-mvp.en.md`
  - 明确 P0 已完成 public model schema split 与 artifact/IO leaf helper split；P0 整体仍未完成。

当前已验证：

```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml translation_events_jsonl_records_blocked_errors
cargo fmt --manifest-path crates/c2r-translator/Cargo.toml -- --check
cargo check --manifest-path crates/c2r-translator/Cargo.toml --all-targets --all-features
cargo test --manifest-path crates/c2r-translator/Cargo.toml
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-frontend
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features "typed-ir clang-frontend"
cargo test --manifest-path crates/c2r-translator/Cargo.toml --all-features
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_run_translator_emit_clang_dry_run_enables_clang_frontend_feature validation.tools.test_auto_migrate.AutoMigrateTests.test_run_translator_emit_clang_dry_run_does_not_enable_lowering_report_feature validation.tools.test_auto_migrate.AutoMigrateTests.test_real_fdb_calc_crc32_emit_clang_dry_run_opt_in_writes_temp_artifact
openspec validate --all --strict
```

结果：

- 定向红绿测试：1 个 `artifact_tests` 测试通过。
- `cargo fmt --check`：exit 0。
- `cargo check --all-targets --all-features`：exit 0。
- 默认 feature：1 个 lib test + 35 个 bounded tests + doc tests 通过。
- `clang-frontend`：1 个 lib test + 44 个 bounded tests + doc tests 通过。
- `typed-ir`：1 个 lib test + 220 个 bounded tests + doc tests 通过。
- `typed-ir clang-frontend`：49 个 lib tests + 395 个 bounded tests + doc tests 通过。
- `--all-features`：57 个 lib tests + 396 个 bounded tests + doc tests 通过。
- Python `--emit-clang-dry-run` opt-in 定向测试：3/3 passed。
- `openspec validate --all --strict`：38/38 passed。

边界：

- 可以说：artifact/IO leaf helper 已从 `lib.rs` 拆出，root public API、artifact 文件名、JSON/JSONL 语义、feature gate 行为和 manifest status 保持兼容。
- 不应说：P0 `lib.rs` 拆分已完成、artifact writer orchestration 已模块化完成、或新增了任何 C 语法翻译能力。
- 后续建议：下一刀可以继续拆 `write_clang_dry_run_artifact()` 这类相对轻的 feature-gated artifact writer；`write_clang_lowering_report_artifact()` 和 `write_translation_artifacts()` 仍要谨慎，因为前者触发 clang lowering/report 语义路径，后者是 public orchestration。

English mirror summary:

- Continued the P0 `lib.rs` split with a behavior-preserving artifact/IO leaf helper extraction.
- Added private `artifacts.rs` containing `write_json_file`, `write_text_file`, and `translation_events_jsonl`, all `pub(crate)`.
- Kept `write_translation_artifacts`, clang dry-run artifact writing, and clang lowering report writing in `lib.rs` for now, preserving the public API, artifact filenames, feature gates, JSON/JSONL semantics, and manifest status behavior.
- Added a blocked JSONL regression test for `translation_events_jsonl`.
- Updated the Chinese and English MVP backlog to mark the model schema split and artifact/IO leaf helper split as done, while keeping the broader P0 `lib.rs` split open.
- Verified default, `clang-frontend`, `typed-ir`, `typed-ir clang-frontend`, and `--all-features` Rust test matrices, selected Python `--emit-clang-dry-run` opt-in tests, and `openspec validate --all --strict`.

## 131. 2026-06-28 P0 clang dry-run artifact writer split

本轮继续拆 `crates/c2r-translator/src/lib.rs` 的 artifact 边界，仍然是行为保持重构，不新增 C 语法翻译能力，不改变 `write_translation_artifacts()` public API、artifact 文件名、manifest status、feature gate 或 Python `--emit-clang-dry-run` opt-in 语义。两个只读子智能体复核后建议一致：`write_clang_dry_run_artifact()` 可以作为轻量 feature-gated artifact writer 迁入 `artifacts.rs`；`write_translation_artifacts()` 和 `write_clang_lowering_report_artifact()` 仍应留在 `lib.rs`，因为前者是 public orchestration，后者会触发 clang lowering/report 语义路径。

核心改动：

- `crates/c2r-translator/src/artifacts.rs`
  - 新增 `#[cfg(feature = "clang-frontend")] pub(crate) fn write_clang_dry_run_artifact(...)`。
  - 保持原 JSON schema：`schema_version`、`target_id`、`slice_id`、`source_commit`、`frontend=clang`、`status`、`dry_run`、`metadata`、`errors`。
  - metadata 完整时仍写 `status=ready_without_libclang`；metadata 缺失时仍写 `status=blocked` 且 `dry_run=null`。
  - 新增模块内单测 `artifacts::clang_dry_run_artifact_tests::clang_dry_run_artifact_records_parse_spec_errors`，直接测试 helper 的 blocked JSON，不重复完整 manifest 流程。
- `crates/c2r-translator/src/lib.rs`
  - `#[cfg(feature = "clang-frontend")] use artifacts::write_clang_dry_run_artifact;`
  - 删除本文件里的旧 `write_clang_dry_run_artifact()` 副本。
  - `PathBuf` import 收窄为只在 `clang-lowering-report` feature 下使用。
  - `write_translation_artifacts()` 调用逻辑保持不变：默认不写 dry-run；`clang-frontend` 下追加 `l3-{slice_id}-clang-dry-run.json`；`clang-lowering-report` 下仍追加 lowering report。
- 同步中英文待办：
  - `docs/c2rust-migration-agent/future-vision-and-mvp.md`
  - `docs/c2rust-migration-agent/future-vision-and-mvp.en.md`
  - P0 仍未完成，只把已完成范围扩展到 feature-gated clang dry-run artifact writer split。

当前已验证：

```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-frontend clang_dry_run_artifact_records_parse_spec_errors
cargo fmt --manifest-path crates/c2r-translator/Cargo.toml -- --check
cargo test --manifest-path crates/c2r-translator/Cargo.toml default_translation_artifacts_do_not_emit_clang_dry_run
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-frontend clang_frontend_feature_writes_dry_run_artifact_from_real_tu_metadata
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-frontend clang_frontend_dry_run_artifact_records_metadata_errors_without_blocking_translation
cargo check --manifest-path crates/c2r-translator/Cargo.toml --all-targets --all-features
cargo test --manifest-path crates/c2r-translator/Cargo.toml
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-frontend
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features "typed-ir clang-frontend"
cargo test --manifest-path crates/c2r-translator/Cargo.toml --all-features
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_run_translator_emit_clang_dry_run_enables_clang_frontend_feature validation.tools.test_auto_migrate.AutoMigrateTests.test_real_fdb_calc_crc32_emit_clang_dry_run_opt_in_writes_temp_artifact
openspec validate --all --strict
```

结果：

- dry-run helper 红绿测试：初始失败于 `write_clang_dry_run_artifact` 不在 `artifacts.rs` 作用域；迁移后通过。
- `cargo fmt --check`：exit 0。
- `cargo check --all-targets --all-features`：exit 0。
- 默认 feature：1 个 lib test + 35 个 bounded tests + doc tests 通过。
- `clang-frontend`：2 个 lib tests + 44 个 bounded tests + doc tests 通过。
- `typed-ir`：1 个 lib test + 220 个 bounded tests + doc tests 通过。
- `typed-ir clang-frontend`：50 个 lib tests + 395 个 bounded tests + doc tests 通过。
- `--all-features`：58 个 lib tests + 396 个 bounded tests + doc tests 通过。
- Python `--emit-clang-dry-run` opt-in 定向测试：2/2 passed。
- `openspec validate --all --strict`：38/38 passed。

边界：

- 可以说：feature-gated clang dry-run artifact writer 已从 `lib.rs` 拆到 `artifacts.rs`，并且默认/opt-in dry-run 行为、manifest 引用和 Python opt-in 路径保持兼容。
- 不应说：P0 `lib.rs` 拆分完成、artifact orchestration 已完全拆出、clang lowering report writer 已拆出、或新增任何 C 语法翻译能力。
- 后续建议：下一刀可以继续拆更明确的 writer/schema helper；`write_clang_lowering_report_artifact()` 要单独处理，因为它不仅写文件，还构造 lowering report、typed IR candidate evidence 和 readonly global summary。`write_translation_artifacts()` 继续留到更后面，等 translator/evidence/orchestration 边界更清楚再移动。

English mirror summary:

- Moved the feature-gated clang dry-run artifact writer into private `artifacts.rs`.
- Kept `write_translation_artifacts` and the clang lowering report writer in `lib.rs`; the former remains public orchestration and the latter still builds lowering/report evidence.
- Added a direct `clang-frontend` module test for the dry-run writer's blocked parse-spec JSON.
- Preserved artifact filenames, manifest behavior, feature gates, and Python `--emit-clang-dry-run` opt-in semantics.
- Updated the Chinese and English MVP backlog to include the dry-run writer split while keeping the broader P0 `lib.rs` split open.

## 132. 2026-06-28 P0 clang lowering report artifact writer split

本轮继续拆 `crates/c2r-translator/src/lib.rs` 的 artifact 边界，仍然是行为保持重构：不新增 C 语法翻译能力，不改变 `write_translation_artifacts()` public API，不改变 artifact 文件名、manifest status、feature gate、Python opt-in 或 semantic pass claim。

两个只读子智能体并行复核后结论一致：

- `write_clang_lowering_report_artifact()`、`typed_ir_candidate_evidence()`、`readonly_global_summary()` 是本轮最小完整迁移集合，可以进入 `artifacts.rs`。
- 不迁移 clang-lowered IR 主翻译路径 helper，因为它们构造 `TranslationResult`、type-map、CFG、pointer graph，并依赖 `lib.rs` 内部翻译/evidence 逻辑。
- `write_translation_artifacts()` 继续留在 `lib.rs`，它仍是 public orchestration，负责选择翻译路径、追加 artifact、组装 manifest status。

核心改动：

- `crates/c2r-translator/src/artifacts.rs`
  - 新增 `#[cfg(feature = "clang-lowering-report")] pub(crate) fn write_clang_lowering_report_artifact(...)`。
  - 同步迁入 `typed_ir_candidate_evidence()` 和 `readonly_global_summary()`。
  - 保持 report JSON schema：`artifact_kind=clang-lowering-report`、`frontend=clang`、`claim_boundary.role=diagnostic_only`、`affects_manifest_status=false`、`affects_semantic_pass=false`、`authoritative_evidence=false`。
  - `typed_ir_candidate.semantic_pass` 仍固定为 `false`，即使能生成 `GenericTypedIr` candidate，也不能把 diagnostic report 当成 semantic acceptance。
  - 新增模块内单测 `artifacts::clang_lowering_report_artifact_tests::clang_lowering_report_artifact_records_parse_spec_errors`，直接覆盖 parse-spec blocked 分支，不把 manifest 责任塞进 writer 单测。
- `crates/c2r-translator/src/lib.rs`
  - 通过 `#[cfg(feature = "clang-lowering-report")] use artifacts::write_clang_lowering_report_artifact;` 调用迁出的 writer。
  - 删除旧的 lowering report artifact writer cluster 副本。
  - `write_translation_artifacts()` 的调用顺序和 manifest status 计算保持不变。
- 同步中英文待办：
  - `docs/c2rust-migration-agent/future-vision-and-mvp.md`
  - `docs/c2rust-migration-agent/future-vision-and-mvp.en.md`
  - P0 总项仍保持未完成，只把 clang lowering report artifact writer cluster 标为已完成子项。

当前已验证：

```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_lowering_report_artifact_records_parse_spec_errors
cargo fmt --manifest-path crates/c2r-translator/Cargo.toml
cargo check --manifest-path crates/c2r-translator/Cargo.toml --all-targets --all-features
cargo test --manifest-path crates/c2r-translator/Cargo.toml
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-frontend
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report
cargo test --manifest-path crates/c2r-translator/Cargo.toml --all-features
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_run_translator_emit_clang_lowering_report_enables_report_feature validation.tools.test_auto_migrate.AutoMigrateTests.test_cache_identity_records_emit_clang_lowering_report_opt_in validation.tools.test_auto_migrate.AutoMigrateTests.test_real_fdb_calc_crc32_emit_clang_lowering_report_opt_in_writes_temp_artifact validation.tools.test_auto_migrate.AutoMigrateTests.test_run_translator_emit_clang_dry_run_does_not_enable_lowering_report_feature
```

结果：

- lowering report writer 红绿测试：初始失败于 `write_clang_lowering_report_artifact` 不在 `artifacts.rs` 作用域；迁移后通过。
- `cargo check --all-targets --all-features`：exit 0。
- 默认 feature：1 个 lib test + 35 个 bounded tests + doc tests 通过。
- `clang-frontend`：2 个 lib tests + 44 个 bounded tests + doc tests 通过。
- `clang-lowering-report`：59 个 lib tests + 396 个 bounded tests + doc tests 通过。
- `--all-features`：59 个 lib tests + 396 个 bounded tests + doc tests 通过。
- Python `--emit-clang-lowering-report` / dry-run non-opt-in 定向测试：4/4 passed。

边界：

- 可以说：clang lowering report artifact writer cluster 已从 `lib.rs` 拆到 `artifacts.rs`，writer 单测、feature 矩阵和 Python opt-in 路径都保持兼容。
- 不应说：P0 `lib.rs` 拆分完成、`write_translation_artifacts()` 已拆出、artifact orchestration 已完全模块化、或新增了任何 C 语法翻译能力。
- 后续建议：下一刀优先从不改变行为的边界继续拆，例如 CLI/manifest helper、unsafe/metadata statistics 或更明确的 evidence builder；翻译主路径和 public orchestration 仍要小步拆，保持每刀 feature matrix 通过。

English mirror summary:

- Moved the clang lowering report artifact writer cluster into private `artifacts.rs`.
- Extracted `write_clang_lowering_report_artifact`, `typed_ir_candidate_evidence`, and `readonly_global_summary` while keeping `write_translation_artifacts` in `lib.rs`.
- Preserved artifact filenames, JSON schema, diagnostic-only claim boundary, manifest status behavior, feature gates, and Python `--emit-clang-lowering-report` opt-in semantics.
- Added a direct module test for the parse-spec blocked report branch.
- Updated the Chinese and English MVP backlog to mark this sub-split done while keeping the broader P0 `lib.rs` split open.

## 133. 2026-06-28 P0 core translation artifact writer helper split

本轮继续拆 `crates/c2r-translator/src/lib.rs` 的 artifact 写出边界，仍然是行为保持重构：不新增 C 语法翻译能力，不改变 `write_translation_artifacts()` public API，不改变 artifact 文件名、artifact 顺序、manifest status、feature gate、Python opt-in 或 semantic pass claim。

两个只读子智能体并行复核后结论一致：

- 当前最适合收口的是 CLI/manifest helper 里的核心 artifact 写出边界，因为已有 Rust/Python 覆盖最强。
- `write_translation_artifacts()` 应继续留在 `lib.rs`，作为 public facade 负责建目录、选择默认/clang-lowered 翻译结果、追加 optional clang artifacts、返回 `ArtifactManifest`。
- 下一刀不要混进本提交；更适合单独做 `clang_lowered_translation.rs` 私有模块，或 metadata/evidence builder 拆分。

核心改动：

- `crates/c2r-translator/src/artifacts.rs`
  - 新增 `pub(crate) fn write_core_translation_artifacts(...)`。
  - 负责写出 8 个核心文件：`auto-translation-plan.json`、`auto-translation-events.jsonl`、`type-map.json`、`cfg.json`、`pointer-graph.json`、`ai-candidate-manifest.json`、`blocked-repairs.json`、`rust-draft.rs`。
  - 保持原有 JSON/JSONL schema、blocked repairs 结构、AI candidate boundary、pointer graph `not_applicable_reason`、type-map status 和 rust draft 文件名不变。
  - 将原 `translation_events_jsonl_records_blocked_errors` 单测迁入 artifact 模块，并新增 `core_translation_artifacts_write_stable_file_set_and_blocked_repairs`。
- `crates/c2r-translator/src/lib.rs`
  - 删除内联核心 artifact 写出列表。
  - 改为调用 `write_core_translation_artifacts(spec, &result, out_dir, &prefix, status)?`。
  - 继续保留 `write_translation_artifacts()` public orchestration，以及 feature-gated `write_clang_dry_run_artifact()` / `write_clang_lowering_report_artifact()` 追加逻辑。
- 同步中英文待办：
  - `docs/c2rust-migration-agent/future-vision-and-mvp.md`
  - `docs/c2rust-migration-agent/future-vision-and-mvp.en.md`
  - P0 总项仍保持未完成，只把 core translation artifact writer helper 标为已完成子项。

当前已验证：

```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml core_translation_artifact_tests
cargo test --manifest-path crates/c2r-translator/Cargo.toml translation_artifacts
cargo check --manifest-path crates/c2r-translator/Cargo.toml --all-targets --all-features
cargo test --manifest-path crates/c2r-translator/Cargo.toml
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-frontend
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report
cargo test --manifest-path crates/c2r-translator/Cargo.toml --all-features
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_route_baseline_and_validation_profile_evidence_are_emitted validation.tools.test_auto_migrate.AutoMigrateTests.test_run_translator_default_does_not_enable_clang_features validation.tools.test_auto_migrate.AutoMigrateTests.test_cache_identity_keeps_clang_lowering_report_fields_out_by_default
cargo fmt --manifest-path crates/c2r-translator/Cargo.toml -- --check
openspec validate --all --strict
git diff --check
```

结果：

- core artifact helper 红绿测试：初始失败于 `write_core_translation_artifacts` 不存在；实现后通过。
- `translation_artifacts` 定向集成测试：artifact 模块单测 + 2 个 bounded translation tests 通过。
- `cargo check --all-targets --all-features`：exit 0。
- 默认 feature：2 个 lib tests + 35 个 bounded tests + doc tests 通过。
- `clang-frontend`：3 个 lib tests + 44 个 bounded tests + doc tests 通过。
- `typed-ir`：2 个 lib tests + 220 个 bounded tests + doc tests 通过。
- `clang-lowering-report`：60 个 lib tests + 396 个 bounded tests + doc tests 通过。
- `--all-features`：60 个 lib tests + 396 个 bounded tests + doc tests 通过。
- Python 默认/route-profile/cache identity 定向测试：3/3 passed。
- `openspec validate --all --strict`：38/38 passed。
- `git diff --check`：exit 0，仅 Windows LF-to-CRLF warnings。

边界：

- 可以说：core translation artifact writer helper 已从 `lib.rs` 拆到 `artifacts.rs`，`write_translation_artifacts()` 现在是更薄的 public facade。
- 不应说：P0 `lib.rs` 拆分完成、`write_translation_artifacts()` 已拆出、CLI/manifest orchestration 已完全模块化、或新增任何 C 语法翻译能力。
- 后续建议：下一刀可单独拆 `clang-lowering-report` 私有翻译/evidence cluster 到 `clang_lowered_translation.rs`，或者按 TDD 先抽 metadata/evidence builder；不要把两者混在同一个提交。

English mirror summary:

- Moved the core translation artifact writer set into private `artifacts.rs` as `write_core_translation_artifacts`.
- Kept `write_translation_artifacts` in `lib.rs` as the public facade that selects the translation path, appends optional clang artifacts, and returns `ArtifactManifest`.
- Preserved artifact filenames, ordering, JSON/JSONL schema, manifest status behavior, feature gates, and Python default/route-profile/cache identity behavior.
- Added a direct module test for the stable core artifact file set and blocked repairs JSON, and moved the JSONL test into the artifacts module.
- Updated the Chinese and English MVP backlog to mark this sub-split done while keeping the broader P0 `lib.rs` split open.

## 134. 2026-06-28 P0 clang-lowered translation module split

本轮继续按 P0 拆分 `crates/c2r-translator/src/lib.rs`，目标是把上一节明确的下一刀落地：将 clang-lowered translation/evidence 私有实现簇移动到单独模块。该提交仍然是行为保持重构，不新增 C 语法翻译能力，不改变 `write_translation_artifacts()` public API，不改变 artifact 顺序、manifest status、feature gate、Python opt-in 或 semantic pass claim。

核心改动：
- 新增 `crates/c2r-translator/src/clang_lowered_translation.rs`。
  - 迁入 `try_translate_slice_with_clang_lowered_ir()`、`record_clang_lowered_ir_evidence()`、`record_ir_*`、`ir_*`、pointer graph helper 和原 clang-lowered evidence 白盒测试。
  - `try_translate_slice_with_clang_lowered_ir()` 仅以 `pub(crate)` 暴露给 crate root wrapper；其余 evidence helper 继续保持模块私有。
  - 模块整体挂在 `#[cfg(feature = "clang-lowering-report")]` 下，继续依赖该 feature 同时启用的 `clang-frontend` 与 `typed-ir`。
- `crates/c2r-translator/src/lib.rs`
  - 保留 `translate_slice_with_optional_clang_lowered_ir()` wrapper、`translate_slice()` legacy fallback 和 `write_translation_artifacts()` public facade。
  - `record_type_mapping()` 改为 `pub(crate)`，供新模块复用既有 type-map 逻辑。
  - 删除 clang-lowered translation/evidence helper 副本和不再需要的 root `BTreeMap` import。
- 同步中英文 MVP 待办：
  - `docs/c2rust-migration-agent/future-vision-and-mvp.md`
  - `docs/c2rust-migration-agent/future-vision-and-mvp.en.md`
  - 将 `lib.rs` 当前规模更新为约 2.6k 行，并把 `clang_lowered_translation.rs` 私有模块拆分列为已完成子项；P0 总项仍保持未完成。

当前已验证：

```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_lowered_translation_module_exposes_fallback_candidate_entrypoint
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_lowered_ir_evidence_tests
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_lowering_report_feature_writes_report_artifact_without_changing_manifest_status
cargo check --manifest-path crates/c2r-translator/Cargo.toml --all-targets --all-features
cargo test --manifest-path crates/c2r-translator/Cargo.toml
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-frontend
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features "typed-ir clang-frontend"
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report
cargo test --manifest-path crates/c2r-translator/Cargo.toml --all-features --quiet
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_route_and_profile_bind_clang_lowered_typed_ir_candidate_evidence validation.tools.test_auto_migrate.AutoMigrateTests.test_run_translator_emit_clang_lowering_report_enables_report_feature validation.tools.test_auto_migrate.AutoMigrateTests.test_cache_identity_records_emit_clang_lowering_report_opt_in
```

结果：
- clang-lowered module entrypoint 红绿测试通过。
- moved evidence 白盒测试通过：8 passed。
- manifest/claim-boundary 集成测试通过。
- `cargo check --all-targets --all-features` exit 0。
- 默认 feature：2 个 lib tests + 35 个 bounded tests + doc tests 通过。
- `clang-frontend`：3 个 lib tests + 44 个 bounded tests + doc tests 通过。
- `typed-ir`：2 个 lib tests + 220 个 bounded tests + doc tests 通过。
- `typed-ir clang-frontend`：51 个 lib tests + 395 个 bounded tests + doc tests 通过。
- `clang-lowering-report`：61 个 lib tests + 396 个 bounded tests + doc tests 通过。
- `--all-features --quiet`：61 个 lib tests + 396 个 bounded tests + doc tests 通过。
- Python clang lowering report route/profile/cache opt-in 定向测试：3/3 passed。

边界：
- 可以说：clang-lowered translation/evidence 私有实现已从 `lib.rs` 拆到 `clang_lowered_translation.rs`，crate root 只保留薄 wrapper 和 public artifact facade。
- 可以说：这是维护性拆分，降低 `lib.rs` 体积和职责耦合，为后续继续拆 CLI/manifest、generic typed IR route、legacy translator、metadata/evidence builder 做准备。
- 不应说：P0 `lib.rs` 拆分完成、translator 架构已完全模块化、支持了新的 C 语法、或任何 generated candidate 因本次拆分获得 semantic pass。

English mirror summary:

- Extracted the private clang-lowered translation/evidence implementation cluster into `clang_lowered_translation.rs`.
- Kept `write_translation_artifacts` and `translate_slice_with_optional_clang_lowered_ir` in `lib.rs` as the public/facade boundary.
- Reused the existing type-map logic through `pub(crate) record_type_mapping` and kept evidence helpers private to the new module.
- Preserved artifact ordering, manifest status behavior, feature gates, Python opt-in behavior, and diagnostic-only semantic claim boundaries.
- Updated the Chinese and English MVP backlog to mark this sub-split done while keeping the broader P0 `lib.rs` split open.

## 135. 2026-06-28 P0 legacy string translator module split

本轮继续按 P0 拆分 `crates/c2r-translator/src/lib.rs`，选择 legacy string translator 作为下一刀。两个只读子智能体对比后结论一致：generic typed IR route 的核心已经在 `typed_ir.rs` / `translation_route.rs`，继续动它会牵动更宽 feature matrix；legacy 字符串 parser/evidence/emitter 仍集中在 `lib.rs`，更适合做一次行为保持拆分。

核心改动：
- 新增 `crates/c2r-translator/src/legacy_translation.rs`。
  - 迁入 `translate_slice()`、`ParsedFunction` / `ParsedStatement` / `StatementKind` / `LValue` 等私有模型、legacy 字符串 parser、CFG/type-map/pointer-graph/call evidence builder、bounded pointer/string translator emitter 和相关 helper。
  - `translate_slice()` 继续通过 crate root `pub use legacy_translation::translate_slice` 暴露，外部 API 不变。
  - `record_type_mapping()` 继续以 `pub(crate)` 通过 crate root re-export 给 `clang_lowered_translation.rs` 复用，避免重复 type-map 逻辑。
- `crates/c2r-translator/src/lib.rs`
  - 当前约 125 行，只保留 module declarations、public model re-export、`translate_slice` re-export、`write_translation_artifacts()` public facade、clang-lowered fallback wrapper 和模块边界测试。
  - `write_translation_artifacts()` 仍负责建目录、选择默认/clang-lowered translation result、追加 optional clang artifacts，并返回 `ArtifactManifest`。
- 同步中英文 MVP 待办：
  - `docs/c2rust-migration-agent/future-vision-and-mvp.md`
  - `docs/c2rust-migration-agent/future-vision-and-mvp.en.md`
  - 将 `lib.rs` 当前规模更新为约 125 行，并把 `legacy_translation.rs` 私有模块拆分列为已完成子项；P0 总项仍保持未完成。

TDD 证据：
- 新增 `legacy_translation_module_tests::legacy_translation_module_exposes_translate_slice_entrypoint`。
- 红测先失败于 `could not find legacy_translation in the crate root`。
- 迁移后同一测试通过，并验证 crate root 内部模块入口可以生成 `pub fn identity(value: i32) -> i32`。

当前已验证：

```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml legacy_translation_module_exposes_translate_slice_entrypoint
cargo fmt --manifest-path crates/c2r-translator/Cargo.toml
cargo fmt --manifest-path crates/c2r-translator/Cargo.toml -- --check
cargo check --manifest-path crates/c2r-translator/Cargo.toml --all-targets --all-features
cargo test --manifest-path crates/c2r-translator/Cargo.toml
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-frontend --quiet
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir --quiet
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features "typed-ir clang-frontend" --quiet
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report
cargo test --manifest-path crates/c2r-translator/Cargo.toml --all-features --quiet
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_route_baseline_and_validation_profile_evidence_are_emitted validation.tools.test_auto_migrate.AutoMigrateTests.test_run_translator_default_does_not_enable_clang_features validation.tools.test_auto_migrate.AutoMigrateTests.test_cache_identity_keeps_clang_lowering_report_fields_out_by_default validation.tools.test_auto_migrate.AutoMigrateTests.test_route_and_profile_bind_clang_lowered_typed_ir_candidate_evidence validation.tools.test_auto_migrate.AutoMigrateTests.test_run_translator_emit_clang_lowering_report_enables_report_feature validation.tools.test_auto_migrate.AutoMigrateTests.test_cache_identity_records_emit_clang_lowering_report_opt_in
```

结果：
- legacy module boundary 红绿测试通过。
- 默认 feature：3 个 lib tests + 35 个 bounded tests + doc tests 通过。
- `cargo fmt --check`：exit 0。
- `cargo check --all-targets --all-features`：exit 0。
- `clang-frontend`：4 个 lib tests + 44 个 bounded tests + doc tests 通过。
- `typed-ir`：3 个 lib tests + 220 个 bounded tests + doc tests 通过。
- `typed-ir clang-frontend`：52 个 lib tests + 395 个 bounded tests + doc tests 通过。
- `clang-lowering-report`：62 个 lib tests + 396 个 bounded tests + doc tests 通过。
- `--all-features --quiet`：62 个 lib tests + 396 个 bounded tests + doc tests 通过。
- Python 默认/clang-lowering-report route/profile/cache opt-in 定向测试：6/6 passed。

边界：
- 可以说：legacy 字符串 translator 私有实现已从 `lib.rs` 拆到 `legacy_translation.rs`，crate root public API 保持兼容。
- 可以说：`lib.rs` 现在主要是 public facade，不再承载 legacy parser/evidence/emitter 细节。
- 不应说：P0 拆分全部完成、CLI/manifest orchestration 已完全模块化、generic typed IR route 已拆完、新增任何 C 语法翻译能力、或任何 candidate 因本次拆分获得 semantic pass。

English mirror summary:

- Extracted the private legacy string translator implementation cluster into `legacy_translation.rs`.
- Kept `translate_slice` available from the crate root through `pub use legacy_translation::translate_slice`.
- Kept `write_translation_artifacts` in `lib.rs` as the public artifact facade and preserved feature-gated clang optional artifact behavior.
- Preserved generated Rust behavior, type-map/CFG/pointer-graph evidence behavior, manifest behavior, feature gates, and semantic claim boundaries.
- Updated the Chinese and English MVP backlog to mark this sub-split done while keeping the broader P0 split open.
