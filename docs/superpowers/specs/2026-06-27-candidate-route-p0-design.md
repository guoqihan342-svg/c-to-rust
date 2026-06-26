# Candidate Route P0 设计

本文是中文主文档。英文版本见 `2026-06-27-candidate-route-p0-design.en.md`。

## 目标

P0 的目标是把 `c2r-translator` 里隐藏在 `emit_rust_from_ir()` 内部的候选生成分流显式化：每次 typed IR 生成 Rust 时，都返回候选路线元数据。P0 不扩大 C 语法覆盖率，不接入 LLM，不接入 Python evidence route decision，也不删除现有 crc32 特例。

成功后，调用方能区分：

- `GenericTypedIr`：普通 typed IR emitter 生成候选。
- `DeprecatedLegacyCrc32`：现有 crc32 canned path 生成候选，但明确标记为 deprecated technical debt。
- `Unsupported`：没有生成候选，错误中带候选路线、原因和建议 fallback。

## 非目标

- 不实现完整 L0/L1/L2/L3/L4 evidence 路由。
- 不修改 `validation/tools/auto_migrate.py` 的 `route_decision`、`validation_profile` 或 `semantic_pass` 逻辑。
- 不落盘 candidate route JSON。
- 不接 C2Rust baseline/repair。
- 不接 LLM candidate。
- 不新增 crc32 专用匹配能力。
- 不删除 `is_crc32_byte_cursor_ir()` 或 `emit_crc32_byte_cursor_rust()`。
- 不处理 `static const uint32_t crc32_table[256]` 的 generic global table lowering。

## 当前问题

现在 [typed_ir.rs](../../../crates/c2r-translator/src/typed_ir.rs) 的入口大致是：

```rust
pub fn emit_rust_from_ir(function: &IrFunction) -> Result<String, IrEmitError> {
    if is_crc32_byte_cursor_ir(function) {
        return Ok(emit_crc32_byte_cursor_rust(&function.name));
    }

    emit_scalar_rust_from_ir(function).map_err(...)
}
```

这个 `if` 有两个问题：

- route 是隐式的，调用方只能拿到 Rust 字符串，不知道是 legacy crc32 还是 generic typed IR。
- crc32 特例看起来像正常能力，实际是为了保住现有端到端绿线的临时路径。

P0 要解决的是这两个结构问题，而不是马上消灭 crc32 技术债。

## 模块边界

新增文件：

```text
crates/c2r-translator/src/translation_route.rs
```

职责：

- 定义 candidate route 类型。
- 定义 JSON-ready route metadata。
- 选择候选生成实现。
- 为 legacy crc32 route 提供 deprecation metadata 和删除条件。

不负责：

- 不判断 semantic pass。
- 不生成 validation profile。
- 不决定 evidence route level。
- 不写 `validation/evidence/**`。
- 不替代 `validation/tools/auto_migrate.py` 的 `route_decision`。

## 核心类型

```rust
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
pub enum CandidateRoute {
    DeprecatedLegacyCrc32,
    GenericTypedIr,
    Unsupported,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
pub enum CandidateGenerator {
    LegacyCrc32Emitter,
    GenericTypedIrEmitter,
    None,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
pub struct CandidateRouteReason {
    pub code: String,
    pub detail: String,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
pub struct CandidateRouteDecision {
    pub route_id: String,
    pub route: CandidateRoute,
    pub candidate_generator: CandidateGenerator,
    pub reasons: Vec<CandidateRouteReason>,
    pub fallback: Option<CandidateRoute>,
    pub token_cost: u32,
    pub deprecated: bool,
    pub replacement: Option<CandidateRoute>,
    pub delete_when: Vec<String>,
    pub suggested_required_gates: Vec<String>,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
pub struct EmittedRust {
    pub rust: String,
    pub route: CandidateRouteDecision,
}
```

`suggested_required_gates` 只是候选生成层建议，不是验收口径。最终 required gates 仍由 validation profile 决定。

`EmittedRust` 必须派生 `Debug`，因为现有大量 `expect_err()` 测试要求 `Result` 的 Ok 类型实现 `Debug`。

## API 变更

P0 直接修改 public API：

```rust
pub fn emit_rust_from_ir(function: &IrFunction) -> Result<EmittedRust, IrEmitError>
```

成功时：

```rust
Ok(EmittedRust {
    rust,
    route: CandidateRouteDecision { ... },
})
```

失败时：

```rust
Err(IrEmitError {
    reason,
    route: CandidateRouteDecision {
        route: CandidateRoute::Unsupported,
        ...
    },
})
```

`IrEmitError` 需要新增 `route: CandidateRouteDecision` 字段。`Unsupported` 不返回空 Rust；它必须是 `Err`，避免调用方误认为候选已经生成。

## Route 规则

### DeprecatedLegacyCrc32

命中条件保持当前 `is_crc32_byte_cursor_ir(function)` 不变。

输出：

- `route = DeprecatedLegacyCrc32`
- `candidate_generator = LegacyCrc32Emitter`
- `token_cost = 0`
- `deprecated = true`
- `replacement = Some(GenericTypedIr)`
- `suggested_required_gates` 包含 `rustc_smoke`、`existing_crc32_contract_tests`

删除条件以代码常量和文档双写：

```rust
pub const LEGACY_CRC32_DELETE_WHEN: &[&str] = &[
    "readonly global const table IR is supported",
    "real FlashDB crc32 emits through GenericTypedIr",
    "legacy crc32 matcher has no remaining callers",
];
```

P0 不允许扩大 crc32 匹配条件，也不新增 crc32 golden output 能力测试。测试只确认 legacy route 被标记为 deprecated。

### GenericTypedIr

未命中 legacy crc32 时，调用现有 generic typed IR emitter。

成功时：

- `route = GenericTypedIr`
- `candidate_generator = GenericTypedIrEmitter`
- `token_cost = 0`
- `deprecated = false`
- `replacement = None`
- `suggested_required_gates` 包含 `rustc_smoke`、`typed_ir_contract_tests`

### Unsupported

generic emitter 返回错误时，包装为 `IrEmitError`：

- `route = Unsupported`
- `candidate_generator = None`
- `fallback = Some(GenericTypedIr)` 或后续扩展为 `Some(L2BaselineRepair)`，P0 只保留当前 enum。
- `deprecated = false`
- `suggested_required_gates` 为空或包含 `manual_review`

错误的 `reason` 继续保留现有 fail-closed 细节。

## 与 evidence route decision 的关系

本设计新增的是 candidate route，回答：

```text
这个 typed IR 候选 Rust 应该由哪个生成器生成？
```

`validation/tools/auto_migrate.py` 里的 `route_decision` 回答的是：

```text
这个 slice 的候选生成路径、验证 profile、证据绑定状态是什么？
```

二者不能混用：

- candidate route 不设置 `semantic_pass`。
- candidate route 不设置 `validation_profile`。
- candidate route 不让 L4/refuse 语义覆盖 evidence 层。
- evidence route decision 仍然是 acceptance boundary。

## 代码影响

需要修改：

- `crates/c2r-translator/src/translation_route.rs`
  - 新增。
- `crates/c2r-translator/src/typed_ir.rs`
  - 引入 route 类型。
  - 修改 `emit_rust_from_ir()` 返回 `EmittedRust`。
  - `IrEmitError` 增加 route 字段。
- `crates/c2r-translator/src/lib.rs`
  - 更新调用点，使用 `emitted.rust`。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 约 70 个 `emit_rust_from_ir()` 调用点需要更新。
  - 所有成功调用从 `rust` 改为 `emitted.rust`。
  - 所有失败调用断言 `error.route.route == CandidateRoute::Unsupported`。
  - 新增 route metadata contract tests。
- `docs/c2rust-migration-agent/core-translation-architecture.md`
  - 更新架构说明，指出 legacy crc32 已显式为 deprecated candidate route。
- `docs/c2rust-migration-agent/core-translation-architecture.en.md`
  - 英文同步。
- `CONTEXT.md`
  - 追加本轮交接。

不修改：

- `validation/tools/auto_migrate.py`
- `validation/evidence/**`

## 测试策略

最小测试集：

1. legacy crc32 typed IR 仍生成原有 Rust，但 route 是 `DeprecatedLegacyCrc32`，`deprecated = true`，`replacement = Some(GenericTypedIr)`。
2. 普通 scalar/generic typed IR route 是 `GenericTypedIr`，不包含 `crc32_update_byte`。
3. `table[(crc ^ *p++) & 0xff]` 的 pointer-table case route 是 `GenericTypedIr`。
4. 不支持的 typed IR 返回 `Err`，错误 route 是 `Unsupported`，且保留原始 fail-closed reason。
5. 生产调用点 `src/lib.rs` 仍能取到 Rust 字符串并保持原行为。

验证命令：

```powershell
cargo fmt --manifest-path crates/c2r-translator/Cargo.toml
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend --test bounded_translation
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend
```

如果本机 clang 可用，再运行：

```powershell
$env:PATH = 'C:\Program Files\LLVM\bin;' + $env:PATH
$env:CLANG_PATH = 'C:\Program Files\LLVM\bin\clang.exe'
$env:LIBCLANG_PATH = 'C:\Program Files\LLVM\bin\libclang.dll'
$env:C2R_RUN_CLANG_AST_TESTS = '1'
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend --test bounded_translation clang_ast_dump_ -- --nocapture
```

## 风险与缓解

- 风险：API 返回值改动导致大量测试机械失败。
  - 缓解：先集中更新调用点为 `let emitted = ...; let rust = &emitted.rust;`，再加 route assertions。
- 风险：candidate route 和 evidence route decision 概念混淆。
  - 缓解：类型名使用 `CandidateRouteDecision`，文档明确不负责 semantic pass。
- 风险：legacy crc32 被进一步合法化。
  - 缓解：route 名包含 `Deprecated`，代码常量写删除条件，测试只验证 deprecation metadata。
- 风险：P0 膨胀到 L2/L3/完整 L4。
  - 缓解：P0 enum 只包含三条真实执行路线，不实现未来路线。

## 用户审核点

请重点审核：

- 是否接受直接修改 `emit_rust_from_ir()` public API。
- 是否接受 P0 不接 `auto_migrate.py`。
- 是否接受 legacy crc32 在 P0 中保留，但显式标记为 deprecated。
- 是否接受 candidate route 只建议 gates，不决定 validation profile。
