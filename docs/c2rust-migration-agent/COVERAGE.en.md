# C Construct Coverage Inventory

This document honestly lists C language constructs that are "currently supported" and "explicitly unsupported" by the typed IR + clang frontend + generic emitter pipeline. Chinese original: `COVERAGE.md`.

> Principle: honest boundaries are more credible than exaggerated demos. This file is manually curated from the latest code state; if discrepancies exist, the fail-closed tests in `crates/c2r-translator/tests/bounded_translation.rs` are authoritative.
>
> Matrix gate: this human-readable inventory is a reading entrypoint. Coverage claims are now constrained by `validation/translator-coverage-matrix.json` and `validation/tools/translator_coverage_matrix.py`, which require representative positive cases, negative cases, fail-closed reasons, runtime/evidence dimensions, and existing linked paths. The matrix is not a full C99/C11 support percentage or a semantic-pass proof.

## Type System

| C Type | Status | Notes |
|--------|--------|-------|
| `int` | Supported | Maps to `i32`, signed 32-bit |
| `unsigned int` / `uint32_t` | Supported | Maps to `u32`, unsigned 32-bit |
| `uint8_t` / `unsigned char` | Supported | Maps to `u8` |
| `int8_t` / `signed char` | Supported | Maps to `i8` |
| `int16_t` | Supported | Maps to `i16` |
| `uint16_t` | Supported | Maps to `u16` |
| `int64_t` / `uint64_t` | Supported | Maps to `i64` / `u64` |
| `size_t` (clang canonical) | Supported | Maps to `usize` |
| `void` | Supported | Return type and pointer pointee |
| `const void *` (byte cursor) | Narrow | Maps to `&[u8]` only in proven byte cursor scenarios |
| `const T *` (readonly integer pointer) | Narrow | Maps to `&[T]`, read-only |
| `T *` (mutable output pointer) | Narrow | Maps to `&mut [T]` only when used as a write target |
| `struct T *` (mutable record pointer) | Narrow | Maps to `&mut T` only for direct single-pointer scalar field writes/updates/read-after-write, direct if-return fallthrough writes, and statement inc-dec; not a general ownership or alias model |
| plain `char` | Unsupported | Sign unknown, clang frontend rejects |
| `short` / `unsigned short` | Unsupported | Target-dependent spelling, rejected |
| `long` / `unsigned long` | Unsupported | Target ABI width inference not modeled |
| `long long` / `unsigned long long` | Unsupported | Rejected unless a typedef alias |
| `float` / `double` / `long double` | Unsupported | Floating-point entirely unsupported |
| `_Bool` | Unsupported | Not modeled |
| `enum` | Unsupported | Not modeled |
| `union` | Unsupported | Not modeled |
| `struct` (by-value) | Narrow | Dot-field read, simple dot-field assignment, by-value dot-field compound assignment, statement-position dot-field inc/dec, local by-value copy, and whole-record return with a unique named-tag complete direct scalar field inventory; dot-field paths remain minimal-field candidates; whole-record inventory rejects duplicate tags, bitfields, volatile/packed fields, self-pointer/non-scalar fields; pointer member access is limited to the readonly and single-pointer mutable subsets, not general `->`; value-position field updates, multi-pointer alias-sensitive field writes, nesting, anonymous remain unsupported |

## Declarations and Initialization

| Construct | Status | Notes |
|-----------|--------|-------|
| Single scalar decl + init | Supported | `int x = 1;` |
| Single scalar decl without init | Narrow | Only with assignment-before-read proof, including direct if-return branches where every fallthrough path assigns |
| Local record decl + copy init | Narrow | `struct point q = p;`, candidate-only when later scalar field uses are modeled |
| Multi-decl `int a = 1, b = 2;` | Supported | Compound body and for-init |
| `const` local variable | Not explicit | Clang lowers to non-const |
| `static` local variable | Unsupported | Requires static storage model |
| `extern` declaration | Unsupported | Requires cross-file model |
| Compound literal | Unsupported | `(struct point){1, 2}` |
| Designated initializer | Unsupported | `.x = 1, .y = 2` |

## Expressions

| Construct | Status | Notes |
|-----------|--------|-------|
| Integer literal | Supported | Including unsigned suffix |
| Variable reference | Supported | Locals and params |
| `+` `-` `*` `/` `%` | Narrow | Scalar integer, same-type operands required; unsigned-result `+` / `-` / `*` emit explicit `wrapping_add` / `wrapping_sub` / `wrapping_mul`; literal `/ 0` and `% 0` fail closed |
| `&` `\|` `^` `<<` `>>` | Narrow | Scalar integer, shift lhs/result must match; literal negative shift counts, `shift_count >= width`, and signed right shift without a contract fail closed |
| `~` (bitwise not) | Supported | |
| `-value` (unary minus) | Narrow | Signed integer only |
| `!expr` (logical not) | Narrow | Condition and value-position C int 0/1 |
| `==` `!=` `<` `<=` `>` `>=` | Narrow | Condition and value-position C int 0/1 |
| `&&` `\|\|` (short-circuit) | Narrow | Condition and value-position C int 0/1 |
| `?:` (conditional) | Narrow | Pure integer value-position only |
| Integer cast (explicit/implicit) | Narrow | Clang-proven integral cast, source/target both supported integers |
| Function call (direct call) | Narrow | Direct identifier callee only |
| Nested direct call | Narrow | One-level single nested arg only |
| `*p` (deref read) | Narrow | Readonly integer pointer, no side effects |
| `*(p+i)` / `*(i+p)` (offset deref) | Narrow | Readonly integer pointer, integer offset |
| `p[i]` (array subscript) | Narrow | Readonly pointer slice or local/global array |
| `p->field` (arrow member) | Narrow | Readonly `const struct T *p` scalar field reads, null-presence/guarded readonly reads, and direct non-nullable single-pointer mutable `struct T *p` scalar field assignment/compound update/read-after-write/direct if-return fallthrough write/statement inc-dec are supported; multi-pointer aliasing, nullable mutable pointers, read-before-write, ordinary maybe-write reads, writes only on returning branches, loop/complex-path returns, complex bases/targets/RHS, non-scalar fields, value-position inc-dec, `ForStmt` step inc-dec, layout/ABI claims, and semantic acceptance remain unsupported |
| `p.field` (dot member access) | Narrow | By-value record dot-field read, simple `p.field = value`, statement-position `p.field += value` (RHS limited to a simple integer variable, literal, or integer cast), standalone statement-position `p.field++` / `++p.field` / `p.field--` / `--p.field` (base must be a direct by-value record variable and the field must be a supported integer), and field access after local copy only; value-position `p.field++`, complex RHS/base forms, and pointer/alias-sensitive field writes remain unsupported |
| `++` / `--` (value-position) | Unsupported | Statement value-discarded only |
| `p++` / `p--` (statement) | Narrow | Simple integer variable target only |
| `++p` / `--p` (statement) | Narrow | Simple integer variable target only |
| `p->field++` / `--p->field` (statement) | Narrow | Direct single-pointer mutable record pointer scalar field target only; lowered as value-discarded assignment desugar, not raw inc/dec value semantics |
| `*p++` (byte cursor post-increment) | Narrow | Only in proven byte cursor context |
| `&x` (address-of) | Unsupported | |
| `sizeof` | Unsupported | |
| `_Alignof` | Unsupported | |
| `(type){init}` compound literal | Unsupported | |
| Function pointer | Unsupported | |
| Comma expression | Unsupported | |
| Assignment expression (value-position) | Unsupported | Statement only |
| Compound assignment (value-position) | Unsupported | Statement only |
| Whole-record return | Narrow | Candidate-only when unique named `RecordDecl`/`FieldDecl` inventory exists and every direct field is a supported scalar; duplicate tags, bitfields, volatile/packed/self-pointer/non-scalar fields fail closed; not a layout/ABI proof |

## Statements and Control Flow

| Construct | Status | Notes |
|-----------|--------|-------|
| Expression statement | Supported | `value++;` |
| `return` (with/without value) | Supported | |
| `if` / `if-else` | Supported | Including comparison condition |
| `while` | Supported | Including postfix `size--` |
| `do-while` | Supported | |
| `for` (scoped) | Narrow | Simple init/condition/step forms |
| `break` | Narrow | Inside loop body only |
| `continue` | Narrow | Inside loop body only |
| `switch` | Unsupported | Requires CFG + relooper |
| `goto` | Unsupported | Requires CFG + relooper |
| label | Unsupported | |
| `case` / `default` | Unsupported | |

## Arrays

| Construct | Status | Notes |
|-----------|--------|-------|
| Local fixed-size integer array decl | Narrow | `uint32_t table[3] = {1, 2, 3};` |
| Local array subscript read | Narrow | `table[i]` |
| Local array subscript write | Narrow | `table[i] = value;` |
| Global const integer array | Narrow | `static const uint32_t table[] = {...};` |
| Global array subscript read | Narrow | `CRC32_TABLE[index as usize]` |
| Global array subscript write | Unsupported | Readonly global |
| Variable-length array (VLA) | Unsupported | |
| Incomplete array (no initializer) | Unsupported | |
| Array-to-pointer decay | Unsupported | Not modeled |
| Multi-dimensional array | Unsupported | |
| Array as function parameter | Unsupported | Partially covered indirectly by pointer lowering |

## Pointers

| Construct | Status | Notes |
|-----------|--------|-------|
| `const T *` readonly slice | Narrow | Read-only access on params |
| `T *` mutable output slice | Narrow | Write-only access on params |
| `*p` deref read | Narrow | Readonly pointer only |
| `*(p+i)` bounded offset deref | Narrow | Readonly, integer offset |
| `*out = v` deref write | Narrow | Mutable pointer only |
| `out[i] = v` index write | Narrow | Mutable pointer only |
| `*(out+i) = v` offset write | Narrow | Mutable pointer, integer offset |
| `p == NULL` / `p != NULL` | Narrow | Readonly pointer presence check |
| Pointer arithmetic (general) | Unsupported | Bounded offset read/write only |
| Pointer subtraction | Unsupported | |
| Pointer comparison (general) | Unsupported | NULL comparison only |
| Void pointer (general) | Unsupported | Proven byte cursor scenarios only |
| Function pointer | Unsupported | |
| Double/triple pointer | Unsupported | `T **` |
| Pointer cast (non-integer) | Unsupported | |
| `const T *` write | Unsupported | |
| Mutable pointer read | Unsupported | Write-proven pointer cannot be read |
| Nullable pointer deref after check | Unsupported | Cannot use after null check |

## Preprocessor

| Construct | Status | Notes |
|-----------|--------|-------|
| `#include` | Indirect | Clang preprocesses; not in AST |
| `#define` simple constant | Indirect | Clang expands |
| `#define` macro function | Unsupported | Clang-expanded semantics irreversible |
| `#ifdef` / `#if` | Indirect | Controlled by build profile defines |

## C Standard Library

| Function/Header | Status | Notes |
|-----------------|--------|-------|
| Any standard library function | Unsupported | No stub / extern callee proof |

## Key Boundary Notes

1. **All typed IR successes are candidate generation, not semantic pass.** `semantic_pass=false` remains true until independent validation gates accept the exact draft.
2. **Legacy crc32 specialty templates and string recognizer crc32 paths are deleted.** Must not be restored.
3. **Unsigned Add/Sub/Mul**: C unsigned `+` / `-` / `*` emit explicit wrapping Rust operations to avoid debug/release profile divergence; this remains candidate generation and does not replace the C oracle.
4. **Division/modulo**: Literal zero divisors now fail closed; only when the divisor is non-zero by literal or fixture contract constraint can it enter semantic gate discussion. Non-literal divisors still need a slice precondition or evidence contract.
5. **Bitwise/shift**: Literal negative shift counts, `shift_count >= width`, and signed right shift without a contract now fail closed; this does not represent full C bitwise semantics, usual arithmetic conversions, or signed overflow UB parity.
6. **Pointer-to-slice lowering**: Requires audit that the pointer does not escape, is not written to (const case), and has inferrable length.
7. **Mutable pointer write**: Currently has no noalias proof or multi-pointer interaction alias analysis.
8. **Record/struct**: The dot-field path still emits a minimal Rust struct derived from actually accessed fields; it is not C layout/ABI proof. The whole-record return inventory path rejects duplicate tags, bitfields, volatile/packed fields, self-pointer fields, and non-scalar fields; unions and nested/anonymous records still fail closed.
9. **This inventory is manually maintained.** The ultimate authority is the fail-closed tests in `crates/c2r-translator/tests/bounded_translation.rs`.
