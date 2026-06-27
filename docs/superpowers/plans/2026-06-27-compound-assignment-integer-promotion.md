# Compound Assignment Integer Promotion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a narrow clang-proven integer promotion/truncation path for standalone scalar compound assignment without claiming full C usual conversions.

**Status:** Implemented and verified for direct typed IR, clang skeleton lowering, and real clang AST smoke. The same guarded lowering is also available to simple `ForStmt` compound-assignment steps through the existing clang step parser.

**Architecture:** Keep `CompoundAssignOperator` lowering fail-closed unless clang proves target/result and compute types are supported integers. When compute type differs from target type, lower `x += rhs` to `x = ((x as compute_ty) + (rhs as compute_ty)) as target_ty`, so typed IR emits a deterministic Rust candidate while preserving the C compound-assignment final conversion back to the lhs type.

**Tech Stack:** Rust, `c2r-translator`, clang AST JSON frontend, direct typed IR tests, skeleton tests, real clang smoke tests.

---

### Task 1: Red Tests For Promotion Compound Assignment

**Files:**
- Modify: `crates/c2r-translator/tests/bounded_translation.rs`

- [x] **Step 1: Add direct typed IR casted binary test**

Add a direct typed IR test for:

```c
uint8_t inc8(uint8_t value) {
    value = (uint8_t)((int)value + 1);
    return value;
}
```

Expected Rust shape:

```rust
value = (((value as i32) + 1i32) as u8);
```

- [x] **Step 2: Add clang skeleton test**

Add a `ClangStmtSkeleton::CompoundAssign` test where:
- target type is `uint8_t`
- result type is `uint8_t`
- compute lhs/result type is `int`
- RHS is an `int` literal

Expected: it lowers into `Assign` with an outer cast to `u8` and inner binary result `i32`.

- [x] **Step 3: Add real clang smoke**

Add gated real clang AST smoke:

```c
#include <stdint.h>
uint8_t inc8(uint8_t value) { value += 1; return value; }
```

Expected: report lowers, Rust candidate compiles, and emitted Rust contains `value = (((value as i32) + 1i32) as u8);`.

- [x] **Step 4: Verify red**

Run:

```powershell
$env:C2R_RUN_CLANG_AST_TESTS='1'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir compound_assignment_integer_promotion -- --nocapture
```

Observed red before implementation: the real clang smoke failed because `ClangStmtSkeleton::CompoundAssign` did not carry compute types and lowering rejected target/compute mismatches.

### Task 2: Narrow Implementation

**Files:**
- Modify: `crates/c2r-translator/src/clang_frontend.rs`
- Modify: `crates/c2r-translator/src/typed_ir.rs` only if validation helpers need clearer naming.

- [x] **Step 1: Extend clang compound assignment skeleton**

Add fields to `ClangStmtSkeleton::CompoundAssign`:

```rust
result_ty: ClangTypeSkeleton,
compute_lhs_ty: ClangTypeSkeleton,
compute_result_ty: ClangTypeSkeleton,
```

- [x] **Step 2: Accept narrow integer promotion/truncation**

Keep rejecting:
- target/result type mismatch
- non-integer target/result/compute types
- compute lhs/result mismatch
- non-simple-variable targets

Allow target type to differ from compute type only when all involved types are supported integers.

- [x] **Step 3: Lower to explicit typed IR casts**

For `x op= rhs`, lower to:

```rust
Assign {
    target: Var(x: target_ty),
    value: Cast {
        target: target_ty,
        expr: Binary {
            op,
            lhs: Cast { target: compute_ty, expr: Var(x: target_ty), implicit: true },
            rhs: rhs coerced to compute_ty when needed,
            ty: compute_ty,
        },
        implicit: true,
    },
}
```

- [x] **Step 4: Keep current fail-closed boundaries**

Do not support:
- value-position compound assignment
- non-variable targets
- pointer arithmetic
- floating point
- volatile
- full usual arithmetic conversions
- semantic acceptance

### Task 3: Docs, Gates, Commit

**Files:**
- Modify: `CONTEXT.md`
- Modify: `docs/c2rust-migration-agent/README.md`
- Modify: `docs/c2rust-migration-agent/README.en.md`
- Modify: `docs/c2rust-migration-agent/core-translation-architecture.md`
- Modify: `docs/c2rust-migration-agent/core-translation-architecture.en.md`
- Modify: `codex/translator-strengthening-analysis.md`
- Modify: `codex/translator-strengthening-analysis.en.md`

- [x] **Step 1: Update bilingual docs**

Move this exact slice from "compute type mismatch always fail-closed" to "narrow clang-proven integer promotion/truncation for standalone scalar compound assignment".

Keep all broader usual conversions as fail-closed.

- [x] **Step 2: Run gates**

Run:

```powershell
cargo fmt --manifest-path .\crates\c2r-translator\Cargo.toml -- --check
git diff --check
$env:C2R_RUN_CLANG_AST_TESTS='1'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir compound_assignment_integer_promotion -- --nocapture
$env:C2R_RUN_CLANG_AST_TESTS='1'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir,clang-lowering-report -- --nocapture
```

- [x] **Step 3: Commit and push**

Commit message:

```bash
Support narrow compound assignment integer promotion
```
