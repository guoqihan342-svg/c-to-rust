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
| `enum T` | Narrow | Scalar params/returns/value positions lower as `i32` only for complete uniquely named `EnumDecl`s where every enum constant has an explicit non-negative `int` `ConstantExpr.value`, every value fits `i32`, and `build_profile.target.int_width=32`; no target ABI, implicit/negative/computed enum constants, non-i32 ABI, enum pointers/arrays/fields, and Rust enum generation still fail closed |
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
| Other `enum` type surfaces | Unsupported | Enum pointers, arrays, fields, underlying ABI/layout, and Rust enum generation remain unmodeled; parameters, returns, and local scalar values are limited to the target-ABI-bound i32 subset above, and explicit integer enum constants are listed below |
| `union` | Unsupported | Not modeled |
| `struct` (by-value) | Narrow | Dot-field read, simple dot-field assignment, by-value dot-field compound assignment, statement-position dot-field inc/dec, local by-value copy, and whole-record return with a unique named-tag complete direct scalar field inventory; the record-field subset now has no-clang AST fixture replay for by-value dot read/write, readonly arrow read, single-pointer mutable arrow write, and the reduced `fdb_blob_t`-style typedef spelling fallback from clang `desugaredQualType`/`canonicalQualType` to `struct fdb_blob *` plus opt-in real-clang smoke coverage; `real-fdb-blob-make` now has committed L1 recorded / `candidate_generated` provenance evidence (no-clang fixture replay to typed-IR candidate), and the generated Rust draft passes rust-check plus Rust replay over three fixture cases, but this is not a C oracle/diff, layout/ABI proof, or semantic-pass proof; dot-field paths remain minimal-field candidates; whole-record inventory rejects duplicate tags, bitfields, volatile/packed fields, self-pointer/non-scalar fields; pointer member access is limited to the readonly and single-pointer mutable subsets, not general `->`; value-position field updates, multi-pointer alias-sensitive field writes, nesting, anonymous remain unsupported |

## Declarations and Initialization

| Construct | Status | Notes |
|-----------|--------|-------|
| Single scalar decl + init | Supported | `int x = 1;` |
| Local `enum T` scalar decl + init | Narrow | `enum mode current = MODE_A;` lowers to an `i32` local only inside the target-ABI-bound i32 enum subset above; no-clang AST fixture replay covers declaration, `if` comparison, assignment, and return; implicit/negative/computed enum constants, non-i32 ABI, enum pointers/arrays/fields still fail closed |
| Single scalar decl without init | Narrow | Only with assignment-before-read proof, including direct if-return branches where every fallthrough path assigns |
| Local record decl + copy init | Narrow | `struct point q = p;`, candidate-only when later scalar field uses are modeled |
| Multi-decl `int a = 1, b = 2;` | Supported | Compound body and for-init |
| `const` local variable | Not explicit | Clang lowers to non-const |
| `static` local variable | Unsupported | Requires static storage model |
| `extern` declaration | Unsupported | Requires cross-file model |
| Compound literal | Unsupported | `(struct point){1, 2}` |
| Designated initializer | Narrow | Only local fixed-size integer arrays and top-level readonly `static const` fixed-size integer global arrays with clang-semantically-expanded index-designated / sparse initializers, for example `int table[3] = { [1] = 7 };`; unspecified elements are zero-initialized according to C semantics; struct/union field designators, nested initializers, GNU range designators, VLA/incomplete arrays, unexpanded `DesignatedInitExpr`, and non-integer fields still fail closed |

## Expressions

| Construct | Status | Notes |
|-----------|--------|-------|
| Integer literal | Supported | Including unsigned suffix |
| Variable reference | Supported | Locals and params |
| Enum constant reference | Narrow | Only clang AST `DeclRefExpr -> EnumConstantDecl` references whose declaration has an explicit non-negative integer `ConstantExpr.value` plus a matching direct `IntegerLiteral` child are rewritten at the skeleton boundary into typed IR integer literals; the same proven constants can also appear in literal-like initializers for top-level readonly `static const` fixed-size integer global arrays. Implicit enum values, negative values, and computed expressions still fail closed; `enum T` itself is limited to the target-ABI-bound i32 scalar subset above |
| `+` `-` `*` `/` `%` | Narrow | Scalar integer, same-type operands required; clang-proven usual-arithmetic `IntegralCast`/`IntegralPromotion` participates as an explicit IR cast, while mixed-width/signedness operands without that cast fail closed instead of being guessed by the emitter; unsigned-result `+` / `-` / `*` emit explicit `wrapping_add` / `wrapping_sub` / `wrapping_mul`; signed-result `+` / `-` / `*` emit `checked_add` / `checked_sub` / `checked_mul` + `expect(...)`, making no signed overflow a runtime precondition; literal `/ 0` and `% 0` fail closed |
| `&` `\|` `^` `<<` `>>` | Narrow | Scalar integer, shift lhs/result must match; literal negative shift counts, `shift_count >= width`, and signed right shift without a contract fail closed |
| `~` (bitwise not) | Supported | |
| `-value` (unary minus) | Narrow | Signed integer only |
| `!expr` (logical not) | Narrow | Condition and value-position C int 0/1 |
| `==` `!=` `<` `<=` `>` `>=` | Narrow | Condition and value-position C int 0/1 |
| `&&` `\|\|` (short-circuit) | Narrow | Condition and value-position C int 0/1 |
| `?:` (conditional) | Narrow | Pure integer value-position only; clang-proven integral `ImplicitCastExpr` nodes in conditions are preserved only as explicit IR casts |
| Integer cast (explicit/implicit) | Narrow | Clang-proven `IntegralCast` / `IntegralPromotion`, source/target both supported integers; integral `ImplicitCastExpr` nodes in ordinary value contexts, binary usual-arithmetic contexts, direct-call argument contexts, `?:` condition contexts, and `if`/`while`/`do-while`/`for` condition contexts are preserved as explicit IR casts; no-clang AST fixture replay now covers the clang-proven RHS cast in `uint32_t + uint8_t` and the fail-closed boundary when that cast is missing; `FloatingToIntegral`, `IntegralToFloating`, and unknown/missing `ImplicitCastExpr.castKind` in ordinary expressions, argument positions, or conditions fail closed, and only modeled integer casts plus the `LValueToRValue`/`NoOp` skeleton boundary continue |
| Function call (direct call) | Narrow | Direct identifier callees only; user functions such as `helper`/`observe` have no-clang AST fixture replay for bounded direct calls, and clang-proven integer `ImplicitCastExpr` in argument position is preserved as an explicit cast; `assert(int)`, `abs(int)`, target-ABI-bound `strlen(const char *)`, bounded `strnlen(const char *, size_t)`, bounded `memcmp(const void *, const void *, size_t)`, statement-only `memset(dst, byte_literal, size)`, and statement-only `memcpy(out, src, size)` have minimal models, while other reserved C macro/stdlib/extern surfaces still require an explicit model or extern binding and otherwise fail closed |
| Nested direct call | Narrow | One-level single nested arg only |
| `*p` (deref read) | Narrow | Readonly integer pointer, no side effects |
| `*(p+i)` / `*(i+p)` (offset deref) | Narrow | Readonly integer pointer, integer offset |
| `p[i]` (array subscript) | Narrow | Readonly pointer slice or local/global array |
| `p->field` (arrow member) | Narrow | Readonly `const struct T *p` scalar field reads, null-presence/guarded readonly reads, and direct non-nullable single-pointer mutable `struct T *p` scalar field assignment/compound update/read-after-write/direct if-return fallthrough write/statement inc-dec are supported; multi-pointer aliasing, nullable mutable pointers, read-before-write, ordinary maybe-write reads, writes only on returning branches, loop/complex-path returns, complex bases/targets/RHS, non-scalar fields, value-position inc-dec, `ForStmt` step inc-dec, layout/ABI claims, and semantic acceptance remain unsupported |
| `p.field` (dot member access) | Narrow | By-value record dot-field read, simple `p.field = value`, statement-position `p.field += value` (RHS limited to a simple integer variable, literal, or integer cast), standalone statement-position `p.field++` / `++p.field` / `p.field--` / `--p.field` (base must be a direct by-value record variable and the field must be a supported integer), and field access after local copy only; value-position `p.field++`, complex RHS/base forms, and pointer/alias-sensitive field writes remain unsupported |
| `assert(int)` | Narrow | Direct modeled C assert macro calls only; result type must be `void`, with exactly one bounded integer/condition argument; pointer, record, nested call, inc/dec, deref/member, and similar arguments still fail closed |
| `abs(int)` | Narrow | Direct modeled C `int abs(int)` calls only; argument and result types must both be `i32`; emits `checked_abs().expect(...)` so `INT_MIN` is explicit as a runtime precondition; `labs`, `llabs`, `fabs`, errno/locale behavior, and other stdlib variants still fail closed |
| `strlen(const char *)` | Narrow | Direct modeled C `size_t strlen(const char *)` calls only; requires a target ABI profile for `size_t`/`char`/pointer widths, and the argument must be a direct readonly 8-bit char/byte pointer parameter; the Rust candidate scans `&[u8]`/`&[i8]` for the first NUL byte and uses `expect("C strlen precondition violated")` to expose the NUL-termination precondition; NULL, non-8-bit pointers, complex expressions, non-`size_t` results, and other string functions still fail closed |
| `strnlen(const char *, size_t)` | Narrow | Direct modeled C `size_t strnlen(const char *, size_t)` calls and one-level user direct-call arguments only; arguments must be a direct readonly 8-bit char/byte pointer parameter and a `size_t`/`usize` bound; the Rust candidate uses `.get(..max).expect("C strnlen precondition violated")` on the input slice to expose the length precondition, searches only that bounded range for the first NUL byte, and returns the bound when no NUL is found; it participates in the readonly/mutable pointer noalias gate; NULL, non-8-bit pointers, complex expressions, non-size bounds, non-`size_t` results, `strnlen_s`, and other string functions still fail closed |
| `memcmp(const void *, const void *, size_t)` | Narrow | Direct modeled C `int memcmp(left, right, count)` calls only; the result type must be `i32`, the first two arguments must be direct readonly 8-bit pointer parameters, and the third argument must be `size_t`/`usize`; the Rust candidate uses `.get(..count).expect("C memcmp precondition violated")` on both slices to expose the length precondition, then returns the first differing byte's `i32` difference after C `memcmp` unsigned-byte normalization or `0`; NULL, mutable/non-byte pointers, complex pointer expressions, non-size count arguments, non-statement-position `memcpy`/`memset`, `memmove`, and other memory functions still fail closed |
| `memset(void *, int, size_t)` | Narrow | Statement-position `memset(out, byte_literal, count)` only; the result type must be `void`, the destination must be a direct mutable unsigned 8-bit pointer parameter, the byte value only supports literals that fit in unsigned char without truncation (`0..=255`), and the count must be `size_t`/`usize`; the Rust candidate uses `.get_mut(..count).expect("C memset precondition violated").fill(byte as u8)` to expose the length precondition; expression-position calls, non-literal bytes, truncating byte values, `void *`/signed-char/non-byte destinations, complex destination expressions, non-size counts, `memmove`, non-statement-position `memcpy`, and full alias/overlap/FFI ABI semantics still fail closed |
| `memcpy(void *, const void *, size_t)` | Narrow | Statement-position `memcpy(out, src, count)` only; the result type must be `void`, the destination must be a direct mutable unsigned 8-bit pointer parameter, the source must be a direct readonly 8-bit pointer parameter, the count must be `size_t`/`usize`, and the readonly source plus mutable destination must have `restrict` or equivalent noalias proof; the Rust candidate uses `.get_mut(..count).expect("C memcpy destination precondition violated").copy_from_slice(src.get(..count).expect("C memcpy source precondition violated"))` to expose length preconditions and the non-overlapping slice contract; expression-position calls, complex pointer expressions, non-byte pointers, missing noalias/overlap proof, `memmove`, and full FFI ABI semantics still fail closed |
| `++` / `--` (value-position) | Unsupported | Statement value-discarded only |
| `p++` / `p--` (statement) | Narrow | Simple integer variable target only |
| `++p` / `--p` (statement) | Narrow | Simple integer variable target only |
| `p->field++` / `--p->field` (statement) | Narrow | Direct single-pointer mutable record pointer scalar field target only; lowered as value-discarded assignment desugar, not raw inc/dec value semantics |
| `*p++` (byte cursor post-increment) | Narrow | Only in proven byte cursor context |
| `&x` (address-of) | Unsupported | |
| `sizeof` | Narrow | Supports clang `UnaryExprOrTypeTraitExpr` ABI-bound integer type operands, complete fixed-size integer-array type operands, expression operands that carry `argType.qualType`, and pointer type operands when target `pointer_width` is available, such as `sizeof(int)`, `sizeof(long)`, `sizeof(size_t)`, `sizeof(int[3])`, `sizeof(value)`, and `sizeof(const int *)`; lowers to a `size_t`/`usize` integer literal and requires the result to fit the target `size_t` width; expression operands without `argType`, pointer operands without a pointer-width profile, incomplete/VLA arrays, enum/record/struct layout, object operands that need layout evidence, packing, and alignment remain fail-closed |
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
| Expression statement | Supported | `value++;`, `++value;` |
| `return` (with/without value) | Supported | |
| `if` / `if-else` | Supported | Including comparison condition; clang-proven integral `ImplicitCastExpr` nodes in conditions are preserved only as explicit IR casts |
| `while` | Supported | Including postfix `size--` and the narrow prefix `--size` shape; clang-proven integral `ImplicitCastExpr` nodes in conditions are preserved only as explicit IR casts |
| `do-while` | Supported | clang-proven integral `ImplicitCastExpr` nodes in conditions are preserved only as explicit IR casts |
| `for` (scoped) | Narrow | Simple init/condition/step forms; clang-proven integral `ImplicitCastExpr` nodes in conditions are preserved only as explicit IR casts |
| `break` | Narrow | Inside loop body only |
| `continue` | Narrow | Inside loop body only |
| `switch` | Unsupported | Schema-bound CFG/relooper/route refusal evidence, clang AST `source_range` refusal diagnostics, normalized `switch-0 -> case/default` edges, and minimal structured-recovery precondition/refusal evidence exist; full CFG + relooper + Rust candidate lowering are still required before support |
| `goto` | Unsupported | Schema-bound CFG/relooper/route refusal evidence, clang AST `source_range` refusal diagnostics, normalized `goto-* -> label-*` edges, and minimal structured-recovery precondition/refusal evidence exist; full CFG + relooper + Rust candidate lowering are still required before support |
| label | Unsupported | Recorded only as schema-bound CFG/relooper evidence for `goto` refusal; the clang AST fixture now requires refusal reasons to include `source_range` |
| `case` / `default` | Unsupported | Recorded only as schema-bound CFG/relooper evidence for `switch` refusal; the clang AST fixture now requires refusal reasons to include `source_range` |

## Arrays

| Construct | Status | Notes |
|-----------|--------|-------|
| Local fixed-size integer array decl | Narrow | `uint32_t table[3] = {1, 2, 3};`; includes sequential initializers and the restricted index-designated sparse initializer subset; unspecified elements are zero-filled to the declared length, and initializer lengths/indices must be verifiable against the fixed array length |
| Local array subscript read | Narrow | `table[i]` |
| Local array subscript write | Narrow | `table[i] = value;` |
| Global const integer array | Narrow | Top-level readonly `static const uint32_t table[3] = {...};`; includes sequential initializers, restricted index-designated sparse initializers represented by clang-semantic `array_filler`, and explicit non-negative integer enum constant references, producing `IrGlobalInit::IntegerArray` and Rust `const`; non-`static const`, incomplete arrays, non-integer elements, implicit/negative/computed enum constants, unexpanded `DesignatedInitExpr`, nested/struct/union/range designators still fail closed |
| Global array subscript read | Narrow | `CRC32_TABLE[index as usize]` |
| Global array subscript write | Unsupported | Readonly global |
| Variable-length array (VLA) | Unsupported | |
| Incomplete array (no initializer) | Unsupported | |
| Array-to-pointer decay | Narrow | Decay in an `ArraySubscriptExpr` base is consumed by the existing narrow index-access path; `*(local_fixed_array)` as unary deref of a direct complete fixed array DeclRef lowers to `local_fixed_array[0]`; `*(local_fixed_array + integer_expr)` / `*(integer_expr + local_fixed_array)` lowers to a fixed-array index read and uses the fixed-array index emitter; other pointer arithmetic, call arguments, non-direct `DeclRef`, incomplete/VLA/multi-dimensional arrays, complex expressions, and general pointer values still fail closed |
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
| Other standard library functions | Unsupported | No stub / extern callee proof; `assert(int)`, `abs(int)`, `strlen(const char *)`, `strnlen(const char *, size_t)`, `memcmp(const void *, const void *, size_t)`, statement-only `memset(dst, byte_literal, size)`, and statement-only `memcpy(out, src, size)` are the separately listed minimal-model exceptions above |

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
