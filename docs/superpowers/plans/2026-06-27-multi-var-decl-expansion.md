# Multi VarDecl Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Support clang `DeclStmt` nodes containing multiple simple `VarDecl` children in ordinary compound bodies, so C such as `int a = 1, b = 2; return a + b;` lowers to consecutive typed IR declarations.

**Architecture:** Keep `typed_ir.rs` unchanged because consecutive `IrStmt::Decl` emission already works. Add a clang-frontend body-expansion path that can map one `DeclStmt` block item to multiple `ClangStmtSkeleton::Decl` entries, while preserving the existing single-statement API for `ForStmt` init/step and other narrow contexts. Multi `VarDecl` in `ForStmt` init remains fail-closed in this slice.

**Tech Stack:** Rust, `c2r-translator`, clang AST JSON frontend, real clang smoke tests, bilingual docs.

---

### Task 1: Red Tests For Multi VarDecl Body Expansion

**Files:**
- Modify: `crates/c2r-translator/src/clang_frontend.rs`
- Modify: `crates/c2r-translator/tests/bounded_translation.rs`

- [x] **Step 1: Add source unit coverage**

Add a unit test named `compound_body_skeleton_from_ast_expands_multi_var_decl_stmt` that builds this `CompoundStmt` JSON:

```json
{
  "kind": "CompoundStmt",
  "inner": [
    {
      "kind": "DeclStmt",
      "inner": [
        {
          "kind": "VarDecl",
          "name": "a",
          "type": { "qualType": "int" },
          "init": "c",
          "inner": [
            { "kind": "IntegerLiteral", "value": "1", "type": { "qualType": "int" } }
          ]
        },
        {
          "kind": "VarDecl",
          "name": "b",
          "type": { "qualType": "int" },
          "init": "c",
          "inner": [
            { "kind": "IntegerLiteral", "value": "2", "type": { "qualType": "int" } }
          ]
        }
      ]
    },
    {
      "kind": "ReturnStmt",
      "inner": [
        {
          "kind": "BinaryOperator",
          "opcode": "+",
          "type": { "qualType": "int" },
          "inner": [
            { "kind": "DeclRefExpr", "referencedDecl": { "kind": "VarDecl", "name": "a", "type": { "qualType": "int" } }, "type": { "qualType": "int" } },
            { "kind": "DeclRefExpr", "referencedDecl": { "kind": "VarDecl", "name": "b", "type": { "qualType": "int" } }, "type": { "qualType": "int" } }
          ]
        }
      ]
    }
  ]
}
```

Expected body skeleton shape after implementation:

```rust
[
    ClangStmtSkeleton::Decl { name: "a", .. },
    ClangStmtSkeleton::Decl { name: "b", .. },
    ClangStmtSkeleton::Return { .. },
]
```

- [x] **Step 2: Convert real clang negative smoke to positive smoke**

Replace `clang_ast_dump_rejects_multi_var_decl_stmt_when_enabled` with `clang_ast_dump_emits_multi_var_decl_stmt_when_enabled`:

```c
int multi_decl(void) { int a = 1, b = 2; return a + b; }
```

Expected after implementation:

- `report.status == "lowered"`
- typed IR body is `[Decl(a), Decl(b), Return]`
- emitted Rust contains `let mut a: i32 = 1i32;`, `let mut b: i32 = 2i32;`, and `return (a + b);`
- rustc snippet compile passes

- [x] **Step 3: Verify red**

Run:

```powershell
$env:C2R_RUN_CLANG_AST_TESTS='1'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir multi_var_decl -- --nocapture
```

Expected before implementation: the new tests fail because the current `DeclStmt with 2 VarDecl children` path remains unsupported.

### Task 2: Minimal Implementation

**Files:**
- Modify: `crates/c2r-translator/src/clang_frontend.rs`

- [x] **Step 1: Extract a VarDecl helper**

Move the single `VarDecl` parsing body out of `decl_stmt_skeleton_from_ast()` into a helper:

```rust
fn var_decl_skeleton_from_ast(var_decl: &Value) -> Result<ClangStmtSkeleton, ClangFrontendError>
```

The helper must preserve current behavior for name, type, optional initializer, initializer marker without child, multiple initializer children, and initializer expression lowering.

- [x] **Step 2: Add body statement expansion**

Add:

```rust
fn body_stmt_skeletons_from_ast(stmt: &Value) -> Result<Vec<ClangStmtSkeleton>, ClangFrontendError>
```

For `DeclStmt`, collect `VarDecl` children. If there are zero children, return one `Unsupported` skeleton with the existing reason. If there are one or more children, parse each `VarDecl` through the helper and return the resulting list in source order. For all other statements, return `vec![stmt_skeleton_from_ast(stmt)?]`.

- [x] **Step 3: Use expansion only in compound bodies**

Change `compound_body_skeleton_from_ast()` to append all `body_stmt_skeletons_from_ast()` results. Do not change `stmt_skeleton_from_ast()`, `for_init_stmt_skeleton_from_ast()`, or `IrStmt::For`; this keeps multi `VarDecl` `for` init out of scope.

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

Document that ordinary compound-body `DeclStmt` nodes with multiple simple `VarDecl` children now expand into consecutive typed IR declarations. Keep the boundary explicit: multi `VarDecl` in `ForStmt` init, unsupported VarDecl type/initializer, VLA, side-effecting unsupported initializer, and semantic acceptance still fail closed.

- [x] **Step 2: Run gates**

Run:

```powershell
cargo fmt --manifest-path .\crates\c2r-translator\Cargo.toml -- --check
git diff --check
$env:C2R_RUN_CLANG_AST_TESTS='1'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir multi_var_decl -- --nocapture
$env:C2R_RUN_CLANG_AST_TESTS='1'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir,clang-lowering-report -- --nocapture
```

- [x] **Step 3: Commit and push**

Commit message:

```bash
Support multi VarDecl lowering
```
