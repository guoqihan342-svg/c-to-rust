# Candidate Route P0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make typed IR Rust emission return explicit candidate route metadata while preserving existing crc32 and generic emitter behavior.

**Architecture:** Add a focused `translation_route.rs` module that owns candidate-generation route metadata only. `typed_ir.rs` remains responsible for IR emission, but `emit_rust_from_ir()` returns `EmittedRust` on success and `IrEmitError` with `Unsupported` route metadata on failure. Evidence acceptance remains in `validation/tools/auto_migrate.py` and is not changed.

**Tech Stack:** Rust 2021, serde/serde_json, existing `c2r-translator` typed-ir and clang-frontend feature tests, PowerShell verification commands.

---

## File Structure

- Create `crates/c2r-translator/src/translation_route.rs`
  - Owns `CandidateRoute`, `CandidateGenerator`, `CandidateRouteReason`, `CandidateRouteDecision`, `EmittedRust`, route constructors, and `LEGACY_CRC32_DELETE_WHEN`.
- Modify `crates/c2r-translator/src/lib.rs`
  - Export `translation_route` behind `typed-ir`.
  - Update production call sites to use `emitted.rust`.
- Modify `crates/c2r-translator/src/typed_ir.rs`
  - Import route types and constructors.
  - Change `IrEmitError` to carry `CandidateRouteDecision`.
  - Change `emit_rust_from_ir()` return type to `Result<EmittedRust, IrEmitError>`.
- Modify `crates/c2r-translator/tests/bounded_translation.rs`
  - Add route metadata tests.
  - Update existing call sites to use `.rust`.
  - Assert unsupported failures carry `CandidateRoute::Unsupported` in selected tests.
- Modify `docs/c2rust-migration-agent/core-translation-architecture.md`
  - Describe `translation_route.rs` and deprecated legacy crc32 candidate route.
- Modify `docs/c2rust-migration-agent/core-translation-architecture.en.md`
  - English mirror update.
- Modify `CONTEXT.md`
  - Add handoff entry and verified commands.

## Task 1: Route Metadata Module And Red Tests

**Files:**
- Create: `crates/c2r-translator/src/translation_route.rs`
- Modify: `crates/c2r-translator/src/lib.rs`
- Modify: `crates/c2r-translator/tests/bounded_translation.rs`

- [ ] **Step 1: Write failing route metadata imports and tests**

Add this import near the existing `typed_ir` imports in `crates/c2r-translator/tests/bounded_translation.rs`:

```rust
#[cfg(feature = "typed-ir")]
use c2r_translator::translation_route::{CandidateGenerator, CandidateRoute};
```

Add these tests near `typed_ir_emits_flashdb_crc32_without_string_recognizer`:

```rust
#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_reports_deprecated_legacy_crc32_candidate_route() {
    let emitted = emit_rust_from_ir(&flashdb_crc32_typed_ir()).expect("typed IR crc32 emit");

    assert_eq!(
        emitted.route.route,
        CandidateRoute::DeprecatedLegacyCrc32
    );
    assert_eq!(
        emitted.route.candidate_generator,
        CandidateGenerator::LegacyCrc32Emitter
    );
    assert!(emitted.route.deprecated);
    assert_eq!(
        emitted.route.replacement,
        Some(CandidateRoute::GenericTypedIr)
    );
    assert!(
        emitted
            .route
            .delete_when
            .iter()
            .any(|item| item.contains("readonly global const table IR"))
    );
    assert!(emitted.rust.contains("crc32_update_byte"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_reports_generic_candidate_route_for_scalar_emit() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "add_one_route".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(ir_binary(
                IrBinOp::Add,
                ir_var("value", i32_ty.clone()),
                ir_lit(1, "1", i32_ty.clone()),
                i32_ty,
            )),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit scalar route");

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert_eq!(
        emitted.route.candidate_generator,
        CandidateGenerator::GenericTypedIrEmitter
    );
    assert!(!emitted.route.deprecated);
    assert!(emitted.rust.contains("pub fn add_one_route"));
    assert!(!emitted.rust.contains("crc32_update_byte"));
}
```

- [ ] **Step 2: Run test to verify RED**

Run:

```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend --test bounded_translation typed_ir_reports_ -- --nocapture
```

Expected: compile failure because `c2r_translator::translation_route` and `EmittedRust` do not exist yet, or because `emit_rust_from_ir()` still returns `String`.

- [ ] **Step 3: Add `translation_route.rs` minimal implementation**

Create `crates/c2r-translator/src/translation_route.rs`:

```rust
use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub enum CandidateRoute {
    DeprecatedLegacyCrc32,
    GenericTypedIr,
    Unsupported,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub enum CandidateGenerator {
    LegacyCrc32Emitter,
    GenericTypedIrEmitter,
    None,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct CandidateRouteReason {
    pub code: String,
    pub detail: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
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

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct EmittedRust {
    pub rust: String,
    pub route: CandidateRouteDecision,
}

pub const LEGACY_CRC32_DELETE_WHEN: &[&str] = &[
    "readonly global const table IR is supported",
    "real FlashDB crc32 emits through GenericTypedIr",
    "legacy crc32 matcher has no remaining callers",
];

pub fn deprecated_legacy_crc32_route() -> CandidateRouteDecision {
    CandidateRouteDecision {
        route_id: "deprecated-legacy-crc32-byte-cursor".to_string(),
        route: CandidateRoute::DeprecatedLegacyCrc32,
        candidate_generator: CandidateGenerator::LegacyCrc32Emitter,
        reasons: vec![CandidateRouteReason {
            code: "legacy_crc32_byte_cursor_match".to_string(),
            detail: "temporary crc32 byte-cursor matcher kept as an explicit deprecated candidate route".to_string(),
        }],
        fallback: Some(CandidateRoute::GenericTypedIr),
        token_cost: 0,
        deprecated: true,
        replacement: Some(CandidateRoute::GenericTypedIr),
        delete_when: LEGACY_CRC32_DELETE_WHEN
            .iter()
            .map(|item| (*item).to_string())
            .collect(),
        suggested_required_gates: vec![
            "rustc_smoke".to_string(),
            "existing_crc32_contract_tests".to_string(),
        ],
    }
}

pub fn generic_typed_ir_route() -> CandidateRouteDecision {
    CandidateRouteDecision {
        route_id: "generic-typed-ir".to_string(),
        route: CandidateRoute::GenericTypedIr,
        candidate_generator: CandidateGenerator::GenericTypedIrEmitter,
        reasons: vec![CandidateRouteReason {
            code: "generic_typed_ir_subset".to_string(),
            detail: "typed IR matched the current generic emitter subset".to_string(),
        }],
        fallback: None,
        token_cost: 0,
        deprecated: false,
        replacement: None,
        delete_when: Vec::new(),
        suggested_required_gates: vec![
            "rustc_smoke".to_string(),
            "typed_ir_contract_tests".to_string(),
        ],
    }
}

pub fn unsupported_route(reason: impl Into<String>) -> CandidateRouteDecision {
    CandidateRouteDecision {
        route_id: "unsupported".to_string(),
        route: CandidateRoute::Unsupported,
        candidate_generator: CandidateGenerator::None,
        reasons: vec![CandidateRouteReason {
            code: "outside_typed_ir_emitter_subset".to_string(),
            detail: reason.into(),
        }],
        fallback: Some(CandidateRoute::GenericTypedIr),
        token_cost: 0,
        deprecated: false,
        replacement: None,
        delete_when: Vec::new(),
        suggested_required_gates: vec!["manual_review".to_string()],
    }
}
```

Update `crates/c2r-translator/src/lib.rs` module exports:

```rust
#[cfg(feature = "typed-ir")]
pub mod translation_route;
```

- [ ] **Step 4: Run test again**

Run:

```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend --test bounded_translation typed_ir_reports_ -- --nocapture
```

Expected: still fails until Task 2 changes `emit_rust_from_ir()` to return `EmittedRust`.

## Task 2: Typed IR API Route Return

**Files:**
- Modify: `crates/c2r-translator/src/typed_ir.rs`
- Modify: `crates/c2r-translator/src/lib.rs`
- Test: `crates/c2r-translator/tests/bounded_translation.rs`

- [ ] **Step 1: Change `IrEmitError` and `emit_rust_from_ir()`**

In `crates/c2r-translator/src/typed_ir.rs`, import route helpers:

```rust
use crate::translation_route::{
    deprecated_legacy_crc32_route, generic_typed_ir_route, unsupported_route, EmittedRust,
};
```

Change `IrEmitError`:

```rust
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct IrEmitError {
    pub reason: String,
    pub route: crate::translation_route::CandidateRouteDecision,
}
```

Change `emit_rust_from_ir()`:

```rust
pub fn emit_rust_from_ir(function: &IrFunction) -> Result<EmittedRust, IrEmitError> {
    if is_crc32_byte_cursor_ir(function) {
        return Ok(EmittedRust {
            rust: emit_crc32_byte_cursor_rust(&function.name),
            route: deprecated_legacy_crc32_route(),
        });
    }

    emit_scalar_rust_from_ir(function)
        .map(|rust| EmittedRust {
            rust,
            route: generic_typed_ir_route(),
        })
        .map_err(|detail| {
            let reason = format!(
                "{} is outside the current typed IR emitter subset: {}",
                function.name, detail
            );
            IrEmitError {
                route: unsupported_route(reason.clone()),
                reason,
            }
        })
}
```

- [ ] **Step 2: Update production call site `try_translate_slice_with_clang_lowered_ir`**

In `crates/c2r-translator/src/lib.rs`, change:

```rust
let rust_code = typed_ir::emit_rust_from_ir(function_ir).ok()?;
```

to:

```rust
let rust_code = typed_ir::emit_rust_from_ir(function_ir).ok()?.rust;
```

- [ ] **Step 3: Update typed-ir crc32 bridge**

In `crates/c2r-translator/src/lib.rs`, change:

```rust
typed_ir::emit_rust_from_ir(&ir)
    .expect("hard-coded crc32 typed IR bridge must match the typed IR emitter")
```

to:

```rust
typed_ir::emit_rust_from_ir(&ir)
    .expect("hard-coded crc32 typed IR bridge must match the typed IR emitter")
    .rust
```

- [ ] **Step 4: Run focused route tests**

Run:

```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend --test bounded_translation typed_ir_reports_ -- --nocapture
```

Expected: new route tests pass after existing success call sites in those tests use `emitted.rust`.

## Task 3: Update Existing Typed IR Tests And Add Unsupported Metadata Assertion

**Files:**
- Modify: `crates/c2r-translator/tests/bounded_translation.rs`

- [ ] **Step 1: Mechanically update successful call sites**

For each success pattern:

```rust
let rust = emit_rust_from_ir(&ir).expect("...");
```

change to:

```rust
let emitted = emit_rust_from_ir(&ir).expect("...");
let rust = emitted.rust;
```

For borrowed function IR:

```rust
let emitted = emit_rust_from_ir(function).expect("...");
let rust = emitted.rust;
```

Keep existing `rust.contains(...)` and `assert_rust_snippet_compiles(..., &rust)` assertions.

- [ ] **Step 2: Add route assertions to representative existing tests**

Add to `typed_ir_emits_flashdb_crc32_without_string_recognizer`:

```rust
assert_eq!(emitted.route.route, CandidateRoute::DeprecatedLegacyCrc32);
assert!(emitted.route.deprecated);
```

Add to `typed_ir_emits_crc_update_assignment_with_nested_byte_read`:

```rust
assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
assert!(!emitted.route.deprecated);
```

Add to at least one real clang generic emit test such as `clang_ast_dump_emits_crc_update_assignment_with_pointer_table_when_enabled`:

```rust
assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
```

- [ ] **Step 3: Add unsupported route assertion to one existing fail-closed test**

In `typed_ir_rejects_multiple_post_increment_reads_in_assign_value`, after capturing `error`, add:

```rust
assert_eq!(error.route.route, CandidateRoute::Unsupported);
assert!(
    error
        .route
        .reasons
        .iter()
        .any(|reason| reason.code == "outside_typed_ir_emitter_subset")
);
```

- [ ] **Step 4: Run bounded typed IR tests**

Run:

```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend --test bounded_translation
```

Expected: all bounded translation tests pass, excluding opt-in clang tests that require `C2R_RUN_CLANG_AST_TESTS=1`.

## Task 4: Documentation And Handoff

**Files:**
- Modify: `docs/c2rust-migration-agent/core-translation-architecture.md`
- Modify: `docs/c2rust-migration-agent/core-translation-architecture.en.md`
- Modify: `CONTEXT.md`

- [ ] **Step 1: Update Chinese architecture doc**

In `docs/c2rust-migration-agent/core-translation-architecture.md`, update the emitter route text so it says:

```markdown
P0 后，Rust emitter route 不再是隐藏在 `emit_rust_from_ir()` 里的裸 `if`。`translation_route.rs` 会返回 `CandidateRouteDecision`：

- `GenericTypedIr`：普通 typed IR emitter。
- `DeprecatedLegacyCrc32`：现有 crc32 canned path，显式标记为 deprecated，删除条件由 `LEGACY_CRC32_DELETE_WHEN` 记录。
- `Unsupported`：没有候选 Rust，错误中带 route metadata 和 fail-closed reason。

注意：candidate route 只选择候选生成实现，不决定 `semantic_pass`，也不替代 `validation/tools/auto_migrate.py` 的 evidence `route_decision`。
```

- [ ] **Step 2: Update English architecture doc**

Mirror the same meaning in `docs/c2rust-migration-agent/core-translation-architecture.en.md`:

```markdown
After P0, the Rust emitter route is no longer a hidden `if` inside `emit_rust_from_ir()`. `translation_route.rs` returns a `CandidateRouteDecision`:

- `GenericTypedIr`: the normal typed IR emitter.
- `DeprecatedLegacyCrc32`: the existing crc32 canned path, explicitly deprecated, with delete conditions recorded by `LEGACY_CRC32_DELETE_WHEN`.
- `Unsupported`: no Rust candidate; the error carries route metadata and the fail-closed reason.

Candidate route selects the candidate generation implementation only. It does not decide `semantic_pass` and does not replace the evidence `route_decision` in `validation/tools/auto_migrate.py`.
```

- [ ] **Step 3: Append CONTEXT entry**

Append a new numbered entry to `CONTEXT.md` that records:

```markdown
## 75. 2026-06-27 CandidateRoute P0 skeleton

- Added `crates/c2r-translator/src/translation_route.rs`.
- `emit_rust_from_ir()` now returns `EmittedRust { rust, route }`.
- `IrEmitError` now carries `CandidateRouteDecision` with route `Unsupported`.
- Existing crc32 canned path is preserved but explicitly routed as `DeprecatedLegacyCrc32`.
- Candidate route does not decide semantic acceptance; `validation/tools/auto_migrate.py` remains the evidence route decision boundary.

Verified commands:
...
```

- [ ] **Step 4: Run doc checks**

Run:

```powershell
git diff --check -- docs/c2rust-migration-agent/core-translation-architecture.md docs/c2rust-migration-agent/core-translation-architecture.en.md CONTEXT.md
```

Expected: no whitespace errors.

## Task 5: Full Verification, Review, Commit, Push

**Files:**
- Verify all modified files.

- [ ] **Step 1: Format**

Run:

```powershell
cargo fmt --manifest-path crates/c2r-translator/Cargo.toml
```

Expected: exit code 0.

- [ ] **Step 2: Run bounded translator tests**

Run:

```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend --test bounded_translation
```

Expected: all non-opt-in tests pass.

- [ ] **Step 3: Run full crate tests**

Run:

```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend
```

Expected: lib tests and bounded translation tests pass.

- [ ] **Step 4: Run opt-in clang smoke tests if LLVM exists**

If `C:\Program Files\LLVM\bin\clang.exe` exists, run:

```powershell
$env:PATH = 'C:\Program Files\LLVM\bin;' + $env:PATH
$env:CLANG_PATH = 'C:\Program Files\LLVM\bin\clang.exe'
$env:LIBCLANG_PATH = 'C:\Program Files\LLVM\bin\libclang.dll'
$env:C2R_RUN_CLANG_AST_TESTS = '1'
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend --test bounded_translation clang_ast_dump_ -- --nocapture
```

Expected: all opt-in clang smoke tests pass.

- [ ] **Step 5: Run git checks**

Run:

```powershell
git diff --check
git status -sb --untracked-files=all
```

Expected: no whitespace errors. Status may still show pre-existing `validation/evidence/**` dirty files, but staged files must be limited to Candidate Route P0 changes.

- [ ] **Step 6: Request code review**

Dispatch a reviewer subagent with:

```text
DESCRIPTION: Candidate Route P0 skeleton for typed IR Rust emission.
PLAN_OR_REQUIREMENTS: docs/superpowers/specs/2026-06-27-candidate-route-p0-design.md and this implementation plan.
BASE_SHA: dbb26948cced502ef6238a3d5b9af4aed38edaa9
HEAD_SHA: current HEAD after implementation commit.
```

Address Critical and Important findings before proceeding.

- [ ] **Step 7: Commit and push**

Stage only intended files:

```powershell
git add -- crates/c2r-translator/src/translation_route.rs crates/c2r-translator/src/typed_ir.rs crates/c2r-translator/src/lib.rs crates/c2r-translator/tests/bounded_translation.rs docs/c2rust-migration-agent/core-translation-architecture.md docs/c2rust-migration-agent/core-translation-architecture.en.md CONTEXT.md
git commit -m "Add candidate route metadata to typed IR emission"
git push origin codex/flashdb-rust-skeleton
git ls-remote origin refs/heads/codex/flashdb-rust-skeleton
```

Expected: remote branch points at the new commit.
