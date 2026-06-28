英文镜像见 `2026-06-27-uninitialized-local-decl.en.md`。

# Uninitialized Local Declaration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Support ordinary scalar local declarations without initializers when every later read is definitely preceded by an assignment in the supported straight-line / conservative control-flow subset.

**Architecture:** The clang frontend already lowers `VarDecl` without an initializer to `IrStmt::Decl { init: None }`. The current generic typed IR emitter rejects these declarations. This slice adds a conservative definite-assignment guard before Rust emission, then emits `let mut x: T;` only when unsupported uninitialized reads are ruled out.

**Tech Stack:** Rust, `c2r-translator`, typed IR generic emitter, clang AST JSON smoke tests, bilingual docs.

---

### Task 1: Red Tests

**Files:**
- Modify: `crates/c2r-translator/tests/bounded_translation.rs`

- [x] **Step 1: Add direct typed IR positive coverage**

Add `typed_ir_emits_uninitialized_decl_assigned_before_read`:

```rust
let mut tmp: u32;
tmp = 7u32;
return tmp;
```

Expected after implementation:
- `emit_rust_from_ir()` succeeds.
- Rust contains `let mut tmp: u32;`, `tmp = 7u32;`, and `return tmp;`.
- `assert_rust_snippet_compiles()` passes.

- [x] **Step 2: Keep read-before-assignment negative coverage**

Rename or adjust the existing uninitialized declaration negative test so it proves `int x; return x;` still fails closed because `x` is read before definite assignment, not because uninitialized declarations are globally unsupported.

- [x] **Step 3: Add real clang smoke coverage**

Add `clang_ast_dump_emits_uninitialized_local_decl_assigned_before_read_when_enabled`:

```c
int assign_after_decl(void) {
    int tmp;
    tmp = 7;
    return tmp;
}
```

Expected after implementation:
- `report.status == "lowered"`.
- typed IR body is `[Decl(tmp, init=None), Assign(tmp=7), Return(tmp)]`.
- emitted Rust compiles.

- [x] **Step 4: Verify red**

Run:

```powershell
$env:C2R_RUN_CLANG_AST_TESTS='1'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir uninitialized_local_decl -- --nocapture
```

Expected before implementation: positive tests fail with `decl tmp without initializer is unsupported`.

### Task 2: Minimal Definite-Assignment Guard

**Files:**
- Modify: `crates/c2r-translator/src/typed_ir.rs`

- [x] **Step 1: Add a conservative pre-emission pass**

Track `declared` and `initialized` names. Parameters and readonly globals start initialized. `Decl(init=None)` declares but does not initialize. `Decl(init=Some(_))` validates initializer reads first, then declares and initializes.

- [x] **Step 2: Mark assignment targets initialized after value validation**

For `Assign { target: Var(name), value }`, require the target to be declared, validate reads in `value`, then mark `name` initialized. Assignment to array indices must validate base/index/value reads but does not introduce a new initialized scalar.

- [x] **Step 3: Preserve fail-closed control-flow boundaries**

For `if`, only propagate initialization that is true after both branches. For `while` and `for`, validate bodies in scoped clones and do not assume the loop executes. Do not leak declarations from nested bodies.

- [x] **Step 4: Emit uninitialized scalar declarations**

After the guard, update the scalar `Decl(init=None)` path to emit `let mut name: Ty;` for supported scalar types. Arrays, pointer cursor special-cases, unsupported types, and read-before-assignment remain fail-closed.

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

Document support for ordinary scalar uninitialized local declarations when assigned before read. Explicitly document fail-closed boundaries: read before assignment, branch-only assignment, loop-only assignment, arrays without initializer, pointer/record/function types, semantic acceptance.

- [x] **Step 2: Run gates**

Run:

```powershell
cargo fmt --manifest-path .\crates\c2r-translator\Cargo.toml -- --check
git diff --check
$env:C2R_RUN_CLANG_AST_TESTS='1'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir uninitialized_local_decl -- --nocapture
$env:C2R_RUN_CLANG_AST_TESTS='1'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir,clang-lowering-report -- --nocapture
```

- [x] **Step 3: Commit and push**

Commit message:

```bash
Support assigned uninitialized local declarations
```
