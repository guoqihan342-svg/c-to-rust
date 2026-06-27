# Typed IR Scoped ForStmt Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a narrow scoped typed IR / clang-lowered `ForStmt` candidate generation path without leaking loop-init declarations or mis-modeling `continue`.

**Architecture:** Add a first-class typed IR `For` statement instead of expanding to top-level `Decl + While`. Emit it as a Rust block containing init, `while condition`, body, and step, while keeping loop-init symbols scoped to the block. Clang lowering should only accept simple scalar init, condition expressions already supported by `emit_condition_expr()`, and simple scalar step updates.

**Tech Stack:** Rust, `c2r-translator`, clang AST JSON frontend, direct typed IR tests, real clang gated smoke tests.

---

### Task 1: Direct Typed IR Scoped For

**Files:**
- Modify: `crates/c2r-translator/src/typed_ir.rs`
- Test: `crates/c2r-translator/tests/bounded_translation.rs`

- [x] **Step 1: Write failing direct typed IR tests**

Add tests for:
- `for (int i = 0; i < limit; i = i + 1) { total = total + i; } return total;`
- init declaration does not leak after the loop.
- non-C-int condition result fails closed.

Run:

```powershell
cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features typed-ir typed_ir_for -- --nocapture
```

Expected: compile/test failure because `IrStmt::For` does not exist yet.

- [x] **Step 2: Add `IrStmt::For` and scoped emitter**

Add a typed IR node with:
- `init: Option<Box<IrStmt>>`
- `condition: Option<IrExpr>`
- `step: Option<Box<IrStmt>>`
- `body: Vec<IrStmt>`

Emit as:

```rust
{
    <init>
    while <condition> {
        <body>
        <step>
    }
}
```

The init symbol set must be cloned for the loop block and not written back to the parent scope.

- [x] **Step 3: Update recursive helpers**

Update all typed IR expression/statement traversal helpers touched by statements so `For` is either traversed or rejected explicitly. This includes nullable pointer usage checks, post-increment scans, call evidence scans, and type helpers discovered during implementation.

- [x] **Step 4: Verify direct typed IR tests**

Run:

```powershell
cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features typed-ir typed_ir_for -- --nocapture
```

Expected: direct typed IR `For` tests pass.

### Task 2: Clang ForStmt Skeleton And Lowering

**Files:**
- Modify: `crates/c2r-translator/src/clang_frontend.rs`
- Test: `crates/c2r-translator/tests/bounded_translation.rs`

- [x] **Step 1: Write failing clang skeleton and real clang tests**

Add skeleton and gated real clang smoke for:

```c
int sum_to_limit(int limit) {
    int total = 0;
    for (int i = 0; i < limit; i++) {
        total = total + i;
    }
    return total;
}
```

Add fail-closed smoke for `continue` in a `for` body.

Run:

```powershell
$env:C2R_RUN_CLANG_AST_TESTS='1'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir typed_ir_for -- --nocapture
```

Expected: failure because `ForStmt` is unsupported.

- [x] **Step 2: Add clang skeleton node**

Add `ClangStmtSkeleton::For { init, condition, step, body }`.

Accepted clang subset:
- init: one scalar `DeclStmt` with initializer, or one simple scalar assignment.
- condition: required expression parsed with existing expression skeleton rules.
- step: required postfix scalar inc/dec or simple scalar compound assignment/assignment.
- body: existing supported statement subset.

- [x] **Step 3: Lower skeleton to typed IR**

Lower `ClangStmtSkeleton::For` into `IrStmt::For`.

Lower inc/dec step into equivalent assignment:
- `i++` -> `i = i + 1`
- `i--` -> `i = i - 1`

Reject `continue`, `break`, `goto`, `switch`, empty condition/step slots, condition variable slots, prefix inc/dec steps, calls in conditions, side-effecting conditions, and unsupported body statements.

- [x] **Step 4: Verify clang tests**

Run the same command with `C2R_RUN_CLANG_AST_TESTS=1`.

Expected: skeleton and real clang tests pass; fail-closed `continue` test remains unsupported.

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

Move scoped `ForStmt` from P0 gap to supported narrow candidate generation. Keep `continue`, `break`, unscoped lowering, non-scalar init/step, and usual conversions as fail-closed.

- [x] **Step 2: Run gates**

Run:

```powershell
cargo fmt --manifest-path .\crates\c2r-translator\Cargo.toml -- --check
git diff --check
$env:C2R_RUN_CLANG_AST_TESTS='1'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir typed_ir_for -- --nocapture
$env:C2R_RUN_CLANG_AST_TESTS='1'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir,clang-lowering-report -- --nocapture
```

- [ ] **Step 3: Commit and push**

Commit message:

```bash
Support scoped typed IR ForStmt lowering
```
