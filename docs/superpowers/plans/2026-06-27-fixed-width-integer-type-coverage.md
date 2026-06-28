英文镜像见 `2026-06-27-fixed-width-integer-type-coverage.en.md`。

# Fixed Width Integer Type Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand clang-lowered typed IR coverage for standard fixed-width integer typedef aliases without claiming full C usual conversions or target ABI integer inference.

**Architecture:** Keep the generic typed IR emitter unchanged because it already emits Rust `i8`, `i16`, `i32`, `i64`, `u8`, `u16`, `u32`, and `u64`. Add conservative `type_from_qual_type()` mappings for fixed-width typedef names seen in real AST dumps, then prove real clang functions using these types can lower and compile. Avoid broadening raw C spellings such as plain `char`, `signed char`, `short`, `long`, or `long long` because a full target ABI integer model is outside this slice.

**Tech Stack:** Rust, `c2r-translator`, clang AST JSON frontend, direct clang type unit tests, real clang smoke tests, bilingual docs.

---

### Task 1: Red Tests For Fixed-Width Integer Types

**Files:**
- Modify: `crates/c2r-translator/src/clang_frontend.rs`
- Modify: `crates/c2r-translator/tests/bounded_translation.rs`

- [x] **Step 1: Add direct type parser unit test**

Add a source unit test named `type_from_qual_type_maps_fixed_width_integer_scalars` with these cases:

```rust
[
    ("int8_t", "int8_t", true, 8),
    ("int16_t", "int16_t", true, 16),
    ("uint16_t", "uint16_t", false, 16),
    ("int32_t", "int32_t", true, 32),
    ("int64_t", "int64_t", true, 64),
    ("uint64_t", "uint64_t", false, 64),
]
```

Expected red: unsupported type skeleton for at least `int8_t`, `int16_t`, `uint16_t`, `int64_t`, and `uint64_t`.

- [x] **Step 2: Add real clang smoke**

Add gated real clang AST smoke named `clang_ast_dump_emits_fixed_width_integer_types_when_enabled` with:

```c
#include <stdint.h>
int8_t id_i8(int8_t value) { return value; }
int16_t id_i16(int16_t value) { return value; }
int32_t id_i32(int32_t value) { return value; }
uint16_t id_u16(uint16_t value) { return value; }
int64_t id_i64(int64_t value) { return value; }
uint64_t id_u64(uint64_t value) { return value; }
```

Expected red before implementation: at least one report has `status=unsupported` with a type skeleton reason such as `int16_t is outside the current type skeleton`.

- [x] **Step 3: Add target-dependent spelling negative test**

Add a source unit test named `type_from_qual_type_keeps_target_dependent_integer_spellings_unsupported` proving this slice does not treat raw `signed char`, `short`, `unsigned short`, `long long`, or `unsigned long long` as fixed-width typedef aliases.

- [x] **Step 4: Verify red**

Run:

```powershell
$env:C2R_RUN_CLANG_AST_TESTS='1'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir fixed_width_integer -- --nocapture
```

Expected: fail before the mapping change.

### Task 2: Minimal Implementation

**Files:**
- Modify: `crates/c2r-translator/src/clang_frontend.rs`

- [x] **Step 1: Add signed 8-bit typedef mapping**

Map `int8_t` to signed width 8 with canonical `int8_t`.

- [x] **Step 2: Add signed/unsigned 16-bit typedef mapping**

Map `int16_t` to signed width 16 canonical `int16_t`, and `uint16_t` to unsigned width 16 canonical `uint16_t`.

- [x] **Step 3: Add signed 32-bit alias mapping**

Map `int32_t` to signed width 32 canonical `int32_t` while leaving the existing plain `int` mapping unchanged.

- [x] **Step 4: Add signed/unsigned 64-bit typedef mapping**

Map `int64_t` to signed width 64 canonical `int64_t`, and `uint64_t` to unsigned width 64 canonical `uint64_t`.

- [x] **Step 5: Keep target-dependent types bounded**

Do not add plain `char`, `signed char`, `short`, `unsigned short`, plain `long`, `long long`, or `unsigned long long` in this slice. Leave existing `unsigned char`, `unsigned int`, and `unsigned long` behavior unchanged to avoid unrelated churn in byte-cursor, `uint32_t`, and size-related paths.

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

Document that clang-lowered typed IR now accepts the full current fixed-width typedef alias set `i8/i16/i32/i64/u8/u16/u32/u64`, and that this slice newly adds the signed aliases plus `u16/u64`. Raw target-dependent spellings, full usual conversions, and semantic acceptance still fail closed.

- [x] **Step 2: Run gates**

Run:

```powershell
cargo fmt --manifest-path .\crates\c2r-translator\Cargo.toml -- --check
git diff --check
$env:C2R_RUN_CLANG_AST_TESTS='1'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir fixed_width_integer -- --nocapture
$env:C2R_RUN_CLANG_AST_TESTS='1'; cargo test --manifest-path .\crates\c2r-translator\Cargo.toml --features clang-frontend,typed-ir,clang-lowering-report -- --nocapture
```

- [ ] **Step 3: Commit and push**

Commit message:

```bash
Support fixed-width integer type lowering
```
