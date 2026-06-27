# For Init Multi VarDecl Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Support `for` initializer declaration statements containing multiple simple `VarDecl` children, for example `for (int i = 0, j = 0; i < limit; i++)`, while keeping `step` singular and preserving scoped loop semantics.

**Architecture:** Change typed IR `IrStmt::For.init` from a single optional statement to an ordered `Vec<IrStmt>`. The generic emitter already emits `For` as an outer Rust block plus `while`; it should emit each init statement inside that block before the condition. Clang skeleton `For.init` should mirror this as `Vec<ClangStmtSkeleton>`, using the existing compound-body multi-`VarDecl` expansion helper for `DeclStmt` only in the initializer slot.

**Tech Stack:** Rust, `c2r-translator`, clang AST JSON frontend, generic typed IR emitter, real clang smoke tests, bilingual docs.

---

### Task 1: Red Tests

**Files:**
- Modify: `crates/c2r-translator/tests/bounded_translation.rs`

- [x] **Step 1: Convert real clang reject smoke to positive smoke**

Replace `clang_ast_dump_rejects_typed_ir_for_multi_var_decl_init_when_enabled` with `clang_ast_dump_emits_typed_ir_for_multi_var_decl_init_when_enabled`:

```c
int sum_pair_for(int limit) {
    int total = 0;
    for (int i = 0, j = 0; i < limit; i++) {
        total = total + i + j;
    }
    return total;
}
```

Expected after implementation:
- `report.status == "lowered"`.
- typed IR top-level body is `[Decl(total), For { init: [Decl(i), Decl(j)], ... }, Return(total)]`.
- emitted Rust contains both `let mut i: i32 = 0i32;` and `let mut j: i32 = 0i32;` before the `while`.
- rustc snippet compile passes.

- [x] **Step 2: Verify red**

Run:

```powershell
$env:C2R_RUN_CLANG_AST_TESTS='1'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir multi_var_decl_init -- --nocapture
```

Expected before implementation: the converted smoke fails with `DeclStmt with 2 VarDecl children`.

### Task 2: Minimal Implementation

**Files:**
- Modify: `crates/c2r-translator/src/typed_ir.rs`
- Modify: `crates/c2r-translator/src/clang_frontend.rs`
- Modify: `crates/c2r-translator/src/lib.rs`
- Modify: `crates/c2r-translator/tests/bounded_translation.rs`

- [x] **Step 1: Change For init shape**

Change `IrStmt::For.init` to `Vec<IrStmt>` and `ClangStmtSkeleton::For.init` to `Vec<ClangStmtSkeleton>`. Empty init becomes an empty vec. Keep `step` as `Option<Box<IrStmt>>`.

- [x] **Step 2: Emit multiple init statements in loop scope**

Update `emit_for_stmt()` to validate and emit each init in source order inside the existing outer Rust block before the `while`. The condition, body, and step must see all init declarations; parent scope must not.

- [x] **Step 3: Update traversal helpers**

Update type-mapping, call-expression, byte-cursor, definite-assignment, post-increment, assigned-var collection, and tests to traverse `init: &[IrStmt]`.

- [x] **Step 4: Lower clang DeclStmt init through the multi-VarDecl body helper**

For `ForStmt` init:
- empty slot -> empty vec;
- `DeclStmt` -> expand each simple `VarDecl` in source order;
- `BinaryOperator("=")` -> one assign statement;
- other init kinds remain fail-closed.

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

Document support for `ForStmt` init multiple simple `VarDecl` declarators, and keep boundaries explicit: complex init statements, unsupported types/initializers, VLA/incomplete arrays, condition variable slots, empty condition/step, `continue` / `break`, and semantic acceptance still fail closed.

- [x] **Step 2: Run gates**

Run:

```powershell
cargo fmt --manifest-path .\crates\c2r-translator\Cargo.toml -- --check
git diff --check
$env:C2R_RUN_CLANG_AST_TESTS='1'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir multi_var_decl_init -- --nocapture
$env:C2R_RUN_CLANG_AST_TESTS='1'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir,clang-lowering-report -- --nocapture
```

- [x] **Step 3: Commit and push**

Commit message:

```bash
Support multi VarDecl for-loop init
```
