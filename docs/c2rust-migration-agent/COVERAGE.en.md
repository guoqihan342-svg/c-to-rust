# C Construct Coverage Inventory

This document honestly lists C language constructs that are "currently supported" and "explicitly unsupported" by the typed IR + clang frontend + generic emitter pipeline. Chinese original: `COVERAGE.md`.

> Principle: honest boundaries are more credible than exaggerated demos. This file is manually curated from the latest code state; if discrepancies exist, the fail-closed tests in `crates/c2r-translator/tests/bounded_translation.rs` are authoritative.
>
> Matrix gate: this human-readable inventory is a reading entrypoint. Coverage claims are now constrained by `validation/translator-coverage-matrix.json` and `validation/tools/translator_coverage_matrix.py`, which require representative positive cases, negative cases, fail-closed reasons, runtime/evidence dimensions, and existing linked paths. The matrix is not a full C99/C11 support percentage or a semantic-pass proof.

## Type System

| C Type | Status | Notes |
|--------|--------|-------|
| `int` | Supported | Without a target profile, maps through the existing C baseline as `i32`; profile-aware clang lowering binds `build_profile.target.int_width` so ABI semantics such as `sizeof(int)` are not guessed as fixed 32-bit |
| `unsigned int` / `uint32_t` | Supported | `uint32_t` always maps to `u32`; without a target profile, `unsigned int` maps through the existing C baseline as `u32`, while profile-aware clang lowering binds `build_profile.target.int_width` |
| `uint8_t` / `unsigned char` | Supported | Maps to `u8` |
| `int8_t` / `signed char` | Supported | Maps to `i8` |
| `int16_t` | Supported | Maps to `i16` |
| `uint16_t` | Supported | Maps to `u16` |
| `int64_t` / `uint64_t` | Supported | Maps to `i64` / `u64` |
| `size_t` | Narrow | Maps to `usize` only when `build_profile.target` provides explicit target ABI width evidence; no-profile clang frontend lowering still fails closed and must not guess a fixed 64-bit width |
| `void` | Supported | Return type and pointer pointee |
| `const void *` (byte cursor) | Narrow | Maps to `&[u8]` only in proven byte cursor scenarios |
| `const T *` (readonly integer pointer) | Narrow | Maps to `&[T]` only with read-access evidence such as `*p` / `p[i]` / `*(p+i)` / `*p++`, no writes, no escape, and inferrable length/index bounds; unused or declared-only readonly pointer params fail closed and do not auto-map |
| `T *` (mutable output pointer) | Narrow | Maps to `&mut [T]` only when used as a write target |
| `struct T *` (mutable record pointer) | Narrow | Maps to `&mut T` only for direct single-pointer scalar field writes/updates/read-after-write, direct if-return fallthrough writes, and statement inc-dec; not a general ownership or alias model |
| plain `char` | Unsupported | Sign unknown, clang frontend rejects |
| `short` / `unsigned short` | Unsupported | Target-dependent spelling, rejected |
| `long` / `unsigned long` | Narrow | Modeled only when `build_profile.target.long_width` is explicit; no-profile cases still fail closed |
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
| `+` `-` `*` `/` `%` | Narrow | Scalar integer, same-type operands required; unsigned-result `+` / `-` / `*` emit explicit `wrapping_add` / `wrapping_sub` / `wrapping_mul`; signed-result `+` / `-` / `*` emit `checked_add` / `checked_sub` / `checked_mul` + `expect(...)`, making no signed overflow a runtime precondition; literal `/ 0` and `% 0` fail closed |
| `&` `\|` `^` `<<` `>>` | Narrow | Scalar integer, shift lhs/result must match; literal negative shift counts, `shift_count >= width`, and signed right shift without a contract fail closed |
| `~` (bitwise not) | Supported | |
| `-value` (unary minus) | Narrow | Signed integer only |
| `!expr` (logical not) | Narrow | Condition and value-position C int 0/1 |
| `==` `!=` `<` `<=` `>` `>=` | Narrow | Condition and value-position C int 0/1 |
| `&&` `\|\|` (short-circuit) | Narrow | Condition and value-position C int 0/1 |
| `?:` (conditional) | Narrow | Pure integer value-position only; clang-proven integral `ImplicitCastExpr` nodes in conditions are preserved only as explicit IR casts |
| Integer cast (explicit/implicit) | Narrow | Clang-proven `IntegralCast` / `IntegralPromotion`, source/target both supported integers; integral `ImplicitCastExpr` nodes in ordinary value contexts, direct-call argument contexts, `?:` condition contexts, and `if`/`while`/`do-while`/`for` condition contexts are preserved as explicit IR casts; `FloatingToIntegral`, `IntegralToFloating`, and unknown/missing `ImplicitCastExpr.castKind` in ordinary expressions, argument positions, or conditions fail closed, and only modeled integer casts plus the `LValueToRValue`/`NoOp` skeleton boundary continue |
| Function call (direct call) | Narrow | Direct identifier callees only; user functions such as `helper`/`observe` have no-clang AST fixture replay for bounded direct calls, and clang-proven integer `ImplicitCastExpr` in argument position is preserved as an explicit cast; reserved C macro/stdlib/extern surfaces still require an explicit model or extern binding and otherwise fail closed |
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
| `sizeof` | Narrow | Supports clang `UnaryExprOrTypeTraitExpr` ABI-bound integer type operands, complete fixed-size integer-array type operands, expression operands that carry `argType.qualType`, and pointer type operands when target `pointer_width` is available, such as `sizeof(int)`, `sizeof(long)`, `sizeof(size_t)`, `sizeof(int[3])`, `sizeof(value)`, and `sizeof(const int *)`; lowers to a `size_t`/`usize` integer literal and requires the result to fit the target `size_t` width; expression operands without `argType`, pointer operands without a pointer-width profile, incomplete/VLA arrays, record/struct layout, object operands that need layout evidence, packing, and alignment remain fail-closed |
| `_Alignof` | Unsupported | clang `_Alignof(type)` fails closed explicitly; the current target profile carries width evidence, not an alignment/layout profile, so alignment must not be guessed |
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
| `if` / `if-else` | Supported | Including comparison condition; clang-proven integral `ImplicitCastExpr` nodes in conditions are preserved only as explicit IR casts |
| `while` | Supported | Including postfix `size--`; clang-proven integral `ImplicitCastExpr` nodes in conditions are preserved only as explicit IR casts |
| `do-while` | Supported | clang-proven integral `ImplicitCastExpr` nodes in conditions are preserved only as explicit IR casts |
| `for` (scoped) | Narrow | Simple init/condition/step forms; clang-proven integral `ImplicitCastExpr` nodes in conditions are preserved only as explicit IR casts |
| `break` | Narrow | Inside loop body only |
| `continue` | Narrow | Inside loop body only |
| `switch` | Unsupported | CFG/relooper/route refusal evidence exists; full CFG + relooper still required before lowering |
| `goto` | Unsupported | CFG/relooper/route refusal evidence exists; full CFG + relooper still required before lowering |
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
| Array-to-pointer decay | Skeleton-identified, semantically unmodeled | Preserved as an explicit clang skeleton boundary in ordinary expression position, but typed IR/Rust lowering still fails closed; decay in an `ArraySubscriptExpr` base is consumed only by the existing narrow index-access path |
| Multi-dimensional array | Unsupported | |
| Array as function parameter | Unsupported | Partially covered indirectly by pointer lowering |

## Pointers

| Construct | Status | Notes |
|-----------|--------|-------|
| `const T *` readonly slice | Narrow | Actual read-only parameter access only; missing read-access evidence, including unused readonly pointer params, fails closed |
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
| Pointer value as function argument/return | Unsupported | Ordinary pointer values do not auto-lower to slices, references, or raw pointers; explicit ownership/lifetime/ABI lowering is required |
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
4. **Signed Add/Sub/Mul**: C signed `+` / `-` / `*` emit `checked_*().expect(...)` to carry the no-overflow precondition into candidate Rust; this is still candidate generation/runtime precondition only, does not prove inputs satisfy that precondition, and does not replace slice contracts, evidence fields, the C oracle, or C/Rust diff.
5. **Division/modulo**: Literal zero divisors now fail closed; only when the divisor is non-zero by literal or fixture contract constraint can it enter semantic gate discussion. Non-literal divisors still need a slice precondition or evidence contract.
6. **Bitwise/shift**: Literal negative shift counts, `shift_count >= width`, and signed right shift without a contract now fail closed; this does not represent full C bitwise semantics, usual arithmetic conversions, or signed overflow UB parity.
7. **Pointer-to-slice lowering**: Requires audit that actual read-access evidence exists (`*p`, `p[i]`, `*(p+i)`, `*p++`, etc.), the pointer does not escape, is not written to (const case), and has inferrable length/index bounds. A declared-only `const T *` with no access evidence must fail closed and must not auto-lower to `&[T]`.
8. **Mutable pointer write**: Currently has no noalias proof or multi-pointer interaction alias analysis.
9. **Record/struct**: The dot-field path still emits a minimal Rust struct derived from actually accessed fields; it is not C layout/ABI proof. The whole-record return inventory path rejects duplicate tags, bitfields, volatile/packed fields, self-pointer fields, and non-scalar fields; unions and nested/anonymous records still fail closed.
10. **This inventory is manually maintained.** The ultimate authority is the fail-closed tests in `crates/c2r-translator/tests/bounded_translation.rs`.
