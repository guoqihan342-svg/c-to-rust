# Candidate Route P0 Design

This is the English mirror. The Chinese primary document is `2026-06-27-candidate-route-p0-design.md`.

## Goal

P0 makes candidate-generation routing explicit inside `c2r-translator`. Every typed IR to Rust emission returns route metadata with the generated candidate. P0 does not expand C syntax coverage, connect an LLM, connect the Python evidence route decision, or remove the current crc32 special case.

After P0, callers can distinguish:

- `GenericTypedIr`: the normal typed IR emitter generated the candidate.
- `DeprecatedLegacyCrc32`: the current crc32 canned path generated the candidate, explicitly marked as deprecated technical debt.
- `Unsupported`: no candidate was generated, and the error carries route metadata, reasons, and fallback guidance.

## Non-Goals

- Do not implement the full L0/L1/L2/L3/L4 evidence router.
- Do not modify `validation/tools/auto_migrate.py` route decision, validation profile, or semantic pass logic.
- Do not persist candidate route JSON.
- Do not connect C2Rust baseline or repair.
- Do not connect LLM candidate generation.
- Do not add new crc32-specific matching capability.
- Do not remove `is_crc32_byte_cursor_ir()` or `emit_crc32_byte_cursor_rust()`.
- Do not implement generic lowering for `static const uint32_t crc32_table[256]`.

## Current Problem

The current [typed_ir.rs](../../../crates/c2r-translator/src/typed_ir.rs) entrypoint is effectively:

```rust
pub fn emit_rust_from_ir(function: &IrFunction) -> Result<String, IrEmitError> {
    if is_crc32_byte_cursor_ir(function) {
        return Ok(emit_crc32_byte_cursor_rust(&function.name));
    }

    emit_scalar_rust_from_ir(function).map_err(...)
}
```

This hidden `if` has two problems:

- The route is implicit. Callers only receive a Rust string and cannot tell whether it came from legacy crc32 or generic typed IR.
- The crc32 special case looks like normal translation capability, but it is a temporary path kept to preserve the existing end-to-end green line.

P0 fixes these structural issues without immediately removing the crc32 debt.

## Module Boundary

Create:

```text
crates/c2r-translator/src/translation_route.rs
```

Responsibilities:

- Define candidate route types.
- Define JSON-ready route metadata.
- Select the candidate generation implementation.
- Provide deprecation metadata and delete conditions for the legacy crc32 route.

Not responsible for:

- Determining semantic pass.
- Generating validation profiles.
- Choosing evidence route levels.
- Writing `validation/evidence/**`.
- Replacing `validation/tools/auto_migrate.py` route decisions.

## Core Types

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

`suggested_required_gates` is candidate-layer guidance only. Final required gates remain owned by the validation profile.

`EmittedRust` must derive `Debug` because many existing `expect_err()` tests require the Ok type inside `Result` to implement `Debug`.

## API Change

P0 changes the public API directly:

```rust
pub fn emit_rust_from_ir(function: &IrFunction) -> Result<EmittedRust, IrEmitError>
```

Success:

```rust
Ok(EmittedRust {
    rust,
    route: CandidateRouteDecision { ... },
})
```

Failure:

```rust
Err(IrEmitError {
    reason,
    route: CandidateRouteDecision {
        route: CandidateRoute::Unsupported,
        ...
    },
})
```

`IrEmitError` gains a `route: CandidateRouteDecision` field. `Unsupported` must remain an `Err`; it must not return an empty Rust string.

## Route Rules

### DeprecatedLegacyCrc32

The matching condition remains the current `is_crc32_byte_cursor_ir(function)`.

Output:

- `route = DeprecatedLegacyCrc32`
- `candidate_generator = LegacyCrc32Emitter`
- `token_cost = 0`
- `deprecated = true`
- `replacement = Some(GenericTypedIr)`
- `suggested_required_gates` includes `rustc_smoke` and `existing_crc32_contract_tests`

Delete conditions are duplicated in code and docs:

```rust
pub const LEGACY_CRC32_DELETE_WHEN: &[&str] = &[
    "readonly global const table IR is supported",
    "real FlashDB crc32 emits through GenericTypedIr",
    "legacy crc32 matcher has no remaining callers",
];
```

P0 must not expand crc32 matching conditions or add crc32 golden-output capability tests. Tests should only assert that the legacy route carries deprecation metadata.

### GenericTypedIr

When legacy crc32 does not match, call the existing generic typed IR emitter.

On success:

- `route = GenericTypedIr`
- `candidate_generator = GenericTypedIrEmitter`
- `token_cost = 0`
- `deprecated = false`
- `replacement = None`
- `suggested_required_gates` includes `rustc_smoke` and `typed_ir_contract_tests`

### Unsupported

When the generic emitter returns an error, wrap it in `IrEmitError`:

- `route = Unsupported`
- `candidate_generator = None`
- `fallback = Some(GenericTypedIr)` or later `Some(L2BaselineRepair)`; P0 keeps only the current enum.
- `deprecated = false`
- `suggested_required_gates` is empty or includes `manual_review`

The error `reason` continues to carry the current fail-closed detail.

## Relationship To Evidence Route Decisions

This design adds a candidate route, which answers:

```text
Which generator should produce this typed IR Rust candidate?
```

The `route_decision` in `validation/tools/auto_migrate.py` answers:

```text
What are the slice candidate generation path, validation profile, and evidence binding state?
```

They must not be mixed:

- Candidate route does not set `semantic_pass`.
- Candidate route does not set `validation_profile`.
- Candidate route does not project L4/refuse semantics onto the evidence layer.
- Evidence route decision remains the acceptance boundary.

## Code Impact

Modify:

- `crates/c2r-translator/src/translation_route.rs`
  - New file.
- `crates/c2r-translator/src/typed_ir.rs`
  - Import route types.
  - Change `emit_rust_from_ir()` to return `EmittedRust`.
  - Add route metadata to `IrEmitError`.
- `crates/c2r-translator/src/lib.rs`
  - Update callers to use `emitted.rust`.
- `crates/c2r-translator/tests/bounded_translation.rs`
  - Update roughly 70 `emit_rust_from_ir()` call sites.
  - Update success calls from direct `rust` strings to `emitted.rust`.
  - Assert `error.route.route == CandidateRoute::Unsupported` for failures.
  - Add route metadata contract tests.
- `docs/c2rust-migration-agent/core-translation-architecture.md`
  - Update architecture docs to show legacy crc32 as an explicit deprecated candidate route.
- `docs/c2rust-migration-agent/core-translation-architecture.en.md`
  - English mirror update.
- `CONTEXT.md`
  - Add handoff entry.

Do not modify:

- `validation/tools/auto_migrate.py`
- `validation/evidence/**`

## Test Strategy

Minimum tests:

1. Legacy crc32 typed IR still emits the existing Rust, but route is `DeprecatedLegacyCrc32`, `deprecated = true`, and `replacement = Some(GenericTypedIr)`.
2. Normal scalar/generic typed IR route is `GenericTypedIr` and does not include `crc32_update_byte`.
3. The pointer-table `table[(crc ^ *p++) & 0xff]` case routes through `GenericTypedIr`.
4. Unsupported typed IR returns `Err`; the error route is `Unsupported` and preserves the fail-closed reason.
5. Production call sites in `src/lib.rs` still extract Rust strings and preserve behavior.

Verification commands:

```powershell
cargo fmt --manifest-path crates/c2r-translator/Cargo.toml
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend --test bounded_translation
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend
```

If clang is available locally:

```powershell
$env:PATH = 'C:\Program Files\LLVM\bin;' + $env:PATH
$env:CLANG_PATH = 'C:\Program Files\LLVM\bin\clang.exe'
$env:LIBCLANG_PATH = 'C:\Program Files\LLVM\bin\libclang.dll'
$env:C2R_RUN_CLANG_AST_TESTS = '1'
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend --test bounded_translation clang_ast_dump_ -- --nocapture
```

## Risks And Mitigations

- Risk: the public API return type change causes many mechanical test failures.
  - Mitigation: first update call sites to use `let emitted = ...; let rust = &emitted.rust;`, then add route assertions.
- Risk: candidate route and evidence route decision become confused.
  - Mitigation: use `CandidateRouteDecision` naming and document that it does not own semantic pass.
- Risk: legacy crc32 becomes more legitimate.
  - Mitigation: route name includes `Deprecated`, delete conditions are code constants, and tests assert only deprecation metadata.
- Risk: P0 expands into L2/L3/full L4.
  - Mitigation: P0 enum contains only the three routes that actually execute now.

## Review Points

Please review:

- Whether direct modification of the `emit_rust_from_ir()` public API is acceptable.
- Whether P0 should remain disconnected from `auto_migrate.py`.
- Whether legacy crc32 should remain in P0 but be explicitly marked deprecated.
- Whether candidate route should only suggest gates, leaving validation profile as the acceptance boundary.
