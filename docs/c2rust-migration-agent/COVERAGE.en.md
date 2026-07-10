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
| `enum T` | Narrow | Scalar params/returns/value positions lower as `i32` only for complete uniquely named `EnumDecl`s whose constants are non-negative `int` values proven either by explicit `ConstantExpr.value` or by ordered sibling inference from a known prior value, every value fits `i32`, and `build_profile.target.int_width=32`; no target ABI, negative/computed enum constants, non-i32 ABI, enum pointers/arrays/fields, and Rust enum generation still fail closed |
| `void` | Supported | Return type and pointer pointee |
| `const void *` (byte cursor) | Narrow | Maps to `&[u8]` only in proven byte cursor scenarios |
| `const T *` (readonly integer pointer) | Narrow | Maps to `&[T]` only with read-access evidence such as `*p` / `p[i]` / `*(p+i)` / `*p++`, no writes, no escape, and inferrable length/index bounds; unused or declared-only 8-bit readonly pointer params may remain raw `*const core::ffi::c_void` candidates, but they do not auto-lower to slices; non-8-bit or read readonly pointers still need explicit evidence/alias gates |
| `T *` (mutable output pointer) | Narrow | Maps to `&mut [T]` only when used as a write target |
| `struct T *` (mutable record pointer) | Narrow | Maps to `&mut T` only for direct single-pointer scalar field writes/updates/read-after-write, direct if-return fallthrough writes, statement/simple `ForStmt` step inc-dec, and narrow value-position inc-dec preludes for direct integer fields; statement-position inc-dec is handled only as a value-discarded field assignment; not a general ownership or alias model |
| plain `char` | Unsupported | Sign unknown, clang frontend rejects |
| `short` / `unsigned short` | Unsupported | Target-dependent spelling, rejected |
| `long` / `unsigned long` | Narrow | Modeled only when `build_profile.target.long_width` is explicit; no-profile cases still fail closed |
| `long long` / `unsigned long long` | Unsupported | Rejected unless a typedef alias |
| `float` / `double` / `long double` | Unsupported | Floating-point entirely unsupported |
| `_Bool` | Narrow | Only literal-only `IntegralToBoolean` and direct-call result emission as Rust `bool` are modeled; broader bool storage, pointers, ABI, and mixed integer/bool value semantics still fail closed |
| Other `enum` type surfaces | Unsupported | Enum pointers, arrays, fields, underlying ABI/layout, and Rust enum generation remain unmodeled; parameters, returns, and local scalar values are limited to the target-ABI-bound i32 subset above, and explicit integer enum constants are listed below |
| `union` | Unsupported | Not modeled |
| `struct` (by-value) | Narrow | Dot-field read, simple dot-field assignment, by-value dot-field compound assignment, statement-position dot-field inc/dec, simple `ForStmt` step-position direct dot-field inc/dec, local by-value copy, and whole-record return with a unique named-tag complete direct scalar field inventory; the record-field subset now has no-clang AST fixture replay for by-value dot read/write, readonly arrow read, single-pointer mutable arrow write, and the reduced `fdb_blob_t`-style typedef spelling fallback from clang `desugaredQualType`/`canonicalQualType` to `struct fdb_blob *` plus opt-in real-clang smoke coverage; `real-fdb-blob-make` now has committed typed-IR candidate provenance, exact generated-draft acceptance, and an L4 accepted-evidence semantic pass. `generated_draft_semantic_pass=true` applies only to the SHA-bound exact draft and three-case fixture, whose accepted binding covers C oracle, Rust report, schema diff, negative diff, unsafe scan/ledger, and the observable outputs `return_same_blob` / `blob.buf` / `blob.size`; the route remains L4 refused/accepted-evidence-authoritative, which is not a layout/ABI proof and does not solve `fdb_kv_set` callee semantics; dot-field paths remain minimal-field candidates; whole-record inventory rejects duplicate tags, bitfields, volatile/packed fields, self-pointer/non-scalar fields; pointer member access is limited to the readonly and single-pointer mutable subsets, not general `->`; by-value value-position field updates, multi-pointer alias-sensitive field writes, nesting, anonymous remain unsupported |

## Declarations and Initialization

| Construct | Status | Notes |
|-----------|--------|-------|
| Single scalar decl + init | Supported | `int x = 1;` |
| Local `enum T` scalar decl + init | Narrow | `enum mode current = MODE_A;` lowers to an `i32` local only inside the target-ABI-bound i32 enum subset above; no-clang AST fixture replay covers declaration, `if` comparison, assignment, and return; negative/computed enum constants, non-i32 ABI, enum pointers/arrays/fields still fail closed |
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
| Enum constant reference | Narrow | Clang AST `DeclRefExpr -> EnumConstantDecl` references are rewritten at the skeleton boundary into typed IR integer literals only when the value is a non-negative integer proven by explicit `ConstantExpr.value` plus matching direct `IntegerLiteral`, or inferred from the containing `EnumDecl` sibling order after a known prior value; the same proven constants can also appear in literal-like initializers for top-level readonly `static const` fixed-size integer global arrays. Negative values, computed expressions, and isolated implicit constants without the ordered enum inventory still fail closed; `enum T` itself is limited to the target-ABI-bound i32 scalar subset above |
| `+` `-` `*` `/` `%` | Narrow | Scalar integer, same-type operands required; clang-proven usual-arithmetic `IntegralCast`/`IntegralPromotion` participates as an explicit IR cast, while mixed-width/signedness operands without that cast fail closed instead of being guessed by the emitter; unsigned-result `+` / `-` / `*` emit explicit `wrapping_add` / `wrapping_sub` / `wrapping_mul`; signed-result `+` / `-` / `*` emit `checked_add` / `checked_sub` / `checked_mul` + `expect(...)`, making no signed overflow a runtime precondition; literal `/ 0` and `% 0` fail closed |
| `&` `\|` `^` `<<` `>>` | Narrow | Scalar integer, shift lhs/result must match; literal negative shift counts, `shift_count >= width`, and signed right shift without a contract fail closed |
| `~` (bitwise not) | Supported | |
| `-value` (unary minus) | Narrow | Signed integer only |
| `+value` (unary plus) | Narrow | Integer only; clang-proven `IntegralPromotion` is preserved as an explicit IR cast, and operand/result type mismatches or non-integers fail closed |
| `!expr` (logical not) | Narrow | Condition and value-position C int 0/1 |
| `==` `!=` `<` `<=` `>` `>=` | Narrow | Condition and value-position C int 0/1; value position allows exactly one direct scalar inc/dec operand with an ordered prelude when the other operand is a pure scalar sibling that does not read the modified scalar. Condition position, call/deref/member operands, two side-effect operands, and same-variable sibling reads remain fail-closed |
| `&&` `\|\|` (short-circuit) | Narrow | Condition and value-position C int 0/1 |
| `?:` (conditional) | Narrow | Pure integer value-position only; clang-proven integral `ImplicitCastExpr` nodes in conditions are preserved only as explicit IR casts |
| Integer cast (explicit/implicit) | Narrow | Clang-proven `IntegralCast` / `IntegralPromotion`, source/target both supported integers; integral `ImplicitCastExpr` nodes in ordinary value contexts, binary usual-arithmetic contexts, unary-plus integer-promotion contexts, direct-call argument contexts, `?:` condition contexts, and `if`/`while`/`do-while`/`for` condition contexts are preserved as explicit IR casts; integer `NoOp` in preserved value contexts is also preserved as an explicit `implicit=true` IR cast, while explicit C-style same-width integer `NoOp` casts remain explicit `implicit=false` casts; clang-proven integer value-context `LValueToRValue` is preserved as an explicit typed IR `IrExpr::LValueToRValue` node; no-clang AST fixture replay now covers the clang-proven RHS cast in `uint32_t + uint8_t`, clang-proven `IntegralPromotion` in `+signed_char`, integer `NoOp` return cast, integer `LValueToRValue` return read, and the fail-closed boundary when that cast is missing; `FloatingToIntegral`, `IntegralToFloating`, and unknown/missing `ImplicitCastExpr.castKind` in ordinary expressions, argument positions, or conditions fail closed, and only modeled integer casts plus the integer value-context `LValueToRValue` explicit IR node and non-integer/non-preserved `NoOp` skeleton boundary continue. Pointer, record, and general lvalue-read `LValueToRValue` are outside this capability |
| Function call (direct call) | Narrow | Direct identifier callees only; user functions such as `helper`/`observe` have no-clang AST fixture replay for bounded direct calls, and clang-proven integer `ImplicitCastExpr` in argument position is preserved as an explicit cast; `_Bool` direct-call results may be used in direct or negated condition positions, while ordinary integer-return call truthiness remains fail-closed; `FunctionToPointerDecay` in direct callee position may be consumed as the clang shape for a direct function name or a simple function-pointer parameter callee, and call-argument position only admits direct function-name decay passed to a simple-scalar-signature function-pointer parameter; other value/argument-position decay enters explicit typed IR as `IrExpr::FunctionToPointerDecay` and still fails closed without explicit function-pointer lowering evidence; `assert(int)`, `abs(int)`, target-ABI-bound `strlen(const char *)`, bounded `strnlen(const char *, size_t)`, bounded `memcmp(const void *, const void *, size_t)`, statement-only `memset(dst, byte_literal, size)`, and statement-only `memcpy(out, src, size)` have minimal models, while other reserved C macro/stdlib/extern surfaces still require an explicit model or extern binding and otherwise fail closed |
| Nested direct call | Narrow | Ordinary nested direct calls still support only one immediate single nested arg. Side-effect shapes with an inc/dec leaf support only single-chain multi-layer calls such as `outer(middle(inner(++value)))` / `outer(middle(inner(value++)))`; the leaf is limited to a simple scalar or direct single-pointer mutable record pointer scalar field; each layer may have only one nested direct-call argument, and ordinary arguments mixed into any layer, multiple sibling nested calls, non-chain nested calls, complex inc/dec targets, and other pointer/member/deref side effects still fail closed |
| `*p` (deref read) | Narrow | Readonly integer pointer, no side effects |
| `*(p+i)` / `*(i+p)` (offset deref) | Narrow | Readonly integer pointer, integer offset |
| `p[i]` (array subscript) | Narrow | Readonly pointer slice or local/global array |
| `p->field` (arrow member) | Narrow | Readonly `const struct T *p` scalar field reads, null-presence/guarded readonly reads, and direct non-nullable single-pointer mutable `struct T *p` scalar field assignment/compound update/read-after-write/direct if-return fallthrough write/statement inc-dec/simple `ForStmt` step inc-dec/direct integer field value-position inc-dec are supported; statement-position `p->field++`/`++p->field` emits only when the result is discarded and desugars to a field assignment; multi-pointer aliasing, nullable mutable pointers, read-before-write, ordinary maybe-write reads, writes only on returning branches, loop/complex-path returns, complex bases/targets/RHS, sibling expressions that read the same base, non-scalar fields, layout/ABI claims, and semantic acceptance remain unsupported |
| `p.field` (dot member access) | Narrow | By-value record dot-field read, simple `p.field = value`, statement-position `p.field += value` (RHS limited to a simple integer variable, literal, or integer cast), standalone statement-position and simple `ForStmt` step-position `p.field++` / `++p.field` / `p.field--` / `--p.field` (base must be a direct by-value record variable and the field must be a supported integer), and field access after local copy only; value-position `p.field++`, nested/complex RHS/base forms, pointer-arrow step inc/dec, and pointer/alias-sensitive field writes remain unsupported |
| `assert(int)` | Narrow | Direct modeled C assert macro calls only; result type must be `void`, with exactly one bounded integer/condition argument; pointer, record, nested call, inc/dec, deref/member, and similar arguments still fail closed |
| `abs(int)` | Narrow | Direct modeled C `int abs(int)` calls only; argument and result types must both be `i32`; emits `checked_abs().expect(...)` so `INT_MIN` is explicit as a runtime precondition; `labs`, `llabs`, `fabs`, errno/locale behavior, and other stdlib variants still fail closed |
| `strlen(const char *)` | Narrow | Direct modeled C `size_t strlen(const char *)` calls only; requires a target ABI profile for `size_t`/`char`/pointer widths, and the argument must be a direct readonly 8-bit char/byte pointer parameter; the Rust candidate scans `&[u8]`/`&[i8]` for the first NUL byte and uses `expect("C strlen precondition violated")` to expose the NUL-termination precondition; NULL, non-8-bit pointers, complex expressions, non-`size_t` results, and other string functions still fail closed |
| `strnlen(const char *, size_t)` | Narrow | Direct modeled C `size_t strnlen(const char *, size_t)` calls and one-level user direct-call arguments only; arguments must be a direct readonly 8-bit char/byte pointer parameter and a `size_t`/`usize` bound; the Rust candidate uses `.get(..max).expect("C strnlen precondition violated")` on the input slice to expose the length precondition, searches only that bounded range for the first NUL byte, and returns the bound when no NUL is found; it participates in the readonly/mutable pointer noalias gate; NULL, non-8-bit pointers, complex expressions, non-size bounds, non-`size_t` results, `strnlen_s`, and other string functions still fail closed |
| `memcmp(const void *, const void *, size_t)` | Narrow | Direct modeled C `int memcmp(left, right, count)` calls only; the result type must be `i32`, the first two arguments must be direct readonly 8-bit pointer parameters, and the third argument must be `size_t`/`usize`; the Rust candidate uses `.get(..count).expect("C memcmp precondition violated")` on both slices to expose the length precondition, then returns the first differing byte's `i32` difference after C `memcmp` unsigned-byte normalization or `0`; NULL, mutable/non-byte pointers, complex pointer expressions, non-size count arguments, non-statement-position `memcpy`/`memset`, `memmove`, and other memory functions still fail closed |
| `memset(void *, int, size_t)` | Narrow | Statement-position `memset(out, byte_literal, count)` only; the result type may be legacy IR `void` or real clang/C `void *`, but the return value must be discarded and must not be observed or propagated; the destination must be a direct mutable unsigned 8-bit pointer parameter, the byte value only supports literals that fit in unsigned char without truncation (`0..=255`), and the count must be `size_t`/`usize`; the Rust candidate uses `.get_mut(..count).expect("C memset precondition violated").fill(byte as u8)` to expose the length precondition; expression-position calls, non-literal bytes, truncating byte values, `void *`/signed-char/non-byte destinations, complex destination expressions, non-size counts, `memmove`, non-statement-position `memcpy`, and full alias/overlap/FFI ABI semantics still fail closed |
| `memcpy(void *, const void *, size_t)` | Narrow | Statement-position `memcpy(out, src, count)` only; the result type may be legacy IR `void` or real clang/C `void *`, but the return value must be discarded and must not be observed or propagated; the destination must be a direct mutable unsigned 8-bit pointer parameter, the source must be a direct readonly 8-bit pointer parameter, the count must be `size_t`/`usize`, and the readonly source plus mutable destination must have `restrict` or equivalent noalias proof; the Rust candidate uses `.get_mut(..count).expect("C memcpy destination precondition violated").copy_from_slice(src.get(..count).expect("C memcpy source precondition violated"))` to expose length preconditions and the non-overlapping slice contract; expression-position calls, complex pointer expressions, non-byte pointers, missing noalias/overlap proof, `memmove`, and full FFI ABI semantics still fail closed |
| `++` / `--` (value-position) | Narrow | Simple scalar direct-call/nested direct-call arguments already have narrow preludes; direct single-pointer mutable record pointer scalar fields now support declaration initializer, assignment/return value, and direct-call argument preludes; general value positions, conditions, complex targets, same-base sibling reads, by-value field value positions, and semantic acceptance still fail closed |
| `p++` / `p--` (statement) | Narrow | Simple integer variable target only |
| `++p` / `--p` (statement) | Narrow | Simple integer variable target only |
| `p->field++` / `--p->field` (statement/value) | Narrow | Direct single-pointer mutable record pointer scalar field target only; statement and simple `ForStmt` step forms use value-discarded assignment desugar, while declaration initializer, assignment/return value, and direct-call argument forms may use typed IR value preludes; complex bases/targets, same-base sibling reads, non-scalar fields, and semantic acceptance still fail closed |
| `*p++` (byte cursor post-increment) | Narrow | Only in proven byte cursor context |
| `&x` (address-of) | Unsupported | |
| `sizeof` | Narrow | Supports clang `UnaryExprOrTypeTraitExpr` ABI-bound integer type operands, complete fixed-size integer-array type operands, expression operands that carry `argType.qualType`, and pointer type operands when target `pointer_width` is available, such as `sizeof(int)`, `sizeof(long)`, `sizeof(size_t)`, `sizeof(int[3])`, `sizeof(value)`, and `sizeof(const int *)`; lowers to a `size_t`/`usize` integer literal and requires the result to fit the target `size_t` width; expression operands without `argType`, pointer operands without a pointer-width profile, incomplete/VLA arrays, enum/record/struct layout, object operands that need layout evidence, packing, and alignment remain fail-closed |
| `_Alignof` | Narrow | Supports clang `_Alignof(int)` when `build_profile.target.int_align` provides explicit target alignment evidence; it lowers to a `size_t`/`usize` integer literal and requires the result to fit the target `size_t` width. Missing alignment profile, non-byte-addressable alignment, non-integer types, record/struct layout, packing, and object alignment still fail closed; alignment is never derived from width-only evidence |
| `(type){init}` compound literal | Unsupported | |
| Function pointer | Narrow | Supports simple function-pointer parameter direct callees, for example an `int (*fp)(int)` parameter call `fp(value)` lowers to a Rust `fn(i32) -> i32` parameter and emits `fp(value)`; also supports direct function-name decay as a simple function-pointer argument, for example `apply(helper, value)`; signatures are limited to simple scalar/`void`, and function-pointer variable callees, non-direct function-name passing, storage, returns, complex callees, ABI/FFI, and other argument/value-position `FunctionToPointerDecay` still require explicit function-pointer lowering evidence and fail closed |
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
| Array-to-pointer decay | Narrow | Decay in an `ArraySubscriptExpr` base is consumed by the existing narrow index-access path; `*(local_fixed_array)` as unary deref of a direct complete fixed array DeclRef lowers to `local_fixed_array[0]`; `*(local_fixed_array + integer_expr)` / `*(integer_expr + local_fixed_array)` lowers to a fixed-array index read and uses the fixed-array index emitter; other ordinary `ArrayToPointerDecay` expressions first enter explicit typed IR as `IrExpr::ArrayToPointerDecay`, but pointer arithmetic, call arguments, non-direct `DeclRef`, incomplete/VLA/multi-dimensional arrays, complex expressions, and general pointer values still fail closed without explicit lowering evidence |
| Multi-dimensional array | Unsupported | |
| Array as function parameter | Unsupported | Partially covered indirectly by pointer lowering |

## Pointers

| Construct | Status | Notes |
|-----------|--------|-------|
| `const T *` readonly slice | Narrow | Actual read-only parameter access only; missing read-access evidence does not lower to `&[T]`. Unused 8-bit readonly pointers may remain raw pointer candidates, while non-8-bit or read shapes still fail closed without the slice/noalias evidence they need |
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
| Function pointer | Narrow | Simple-scalar-signature function-pointer parameter direct calls and direct function-name decay as simple function-pointer arguments; function-pointer variable callees, non-direct function-name passing, storage, returns, ABI/FFI, and complex signatures still fail closed |
| Pointer value as function argument/return | Unsupported | Ordinary pointer values do not auto-lower to slices, references, or raw pointers; explicit ownership/lifetime/ABI lowering is required |
| Double/triple pointer | Unsupported | `T **` |
| Pointer cast (non-integer) | Unsupported | |
| `const T *` write | Unsupported | |
| Mutable pointer read | Narrow | Only direct `*out` zero-slot reads from a function parameter `T *out` are supported after a definite write on the same path, emitting `out[0usize]`; read-before-write, offset/index reads, nullable pointers, inout, escape, and complex alias cases still fail closed |
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
7. **Pointer-to-slice lowering**: Requires audit that actual read-access evidence exists (`*p`, `p[i]`, `*(p+i)`, `*p++`, etc.), the pointer does not escape, is not written to (const case), and has inferrable length/index bounds. A declared-only `const T *` with no access evidence must not auto-lower to `&[T]`; the only admitted no-read shape is an unused/unmentioned 8-bit readonly pointer kept as a raw `*const core::ffi::c_void` candidate. Non-8-bit or read readonly pointers still require slice/noalias evidence or fail closed.
8. **Mutable pointer write/read**: Narrow paths exist for a single output pointer and for readonly-input plus mutable-output shapes with explicit `restrict` or slice-spec noalias pairs; direct `*out` reads after a definite write can emit `out[0usize]`. Without noalias proof, multi-pointer/inout, nullable, escaping, volatile/hardware, complex offset/index reads, or complex interactions still fail closed, and there is no complete alias analysis.
9. **Record/struct**: The dot-field path still emits a minimal Rust struct derived from actually accessed fields; it is not C layout/ABI proof. The whole-record return inventory path rejects duplicate tags, bitfields, volatile/packed fields, self-pointer fields, and non-scalar fields; unions and nested/anonymous records still fail closed.
10. **This inventory is manually maintained.** The ultimate authority is the fail-closed tests in `crates/c2r-translator/tests/bounded_translation.rs`.
