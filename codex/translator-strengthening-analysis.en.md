# c-to-rust Translator Strengthening Analysis

> Date: 2026-06-27
> Based on the current `codex/flashdb-rust-skeleton` branch
> Chinese primary: `translator-strengthening-analysis.md`

## Current Judgment

The main diagnosis still holds: **the validation system is stronger than the translator, so the next bottleneck is extending typed IR translation rather than adding more gates.**

Some earlier wording is now stale. The branch no longer needs to "first install clang", typed IR pointer parameters are no longer completely blocked, and `fdb_calc_crc32` is no longer only an L4/refused case. The current branch already has:

- Native LLVM `clang` real AST smoke tests entering `clang_frontend.rs` through `clang -ast-dump=json`.
- `real-fdb-calc-crc32` reaching a `GenericTypedIr` candidate through clang-lowered typed IR plus readonly globals, with rustc smoke passing.
- Readonly integer pointer parameters emitted as Rust slices, for example `const uint32_t *p -> p: &[u32]`.
- Readonly pointer `NULL` presence checks emitted as `Option<&[T]>` plus `.is_none()` / `.is_some()`.
- Direct readonly pointer dereference reads emitted as slice index zero, for example `return *p; -> return p[0usize];`.
- Narrow readonly pointer offset-dereference reads emitted as slice indexes, for example `return *(p+i); -> return p[i as usize];`, also covering `*(i+p)` and literal offsets.
- The clang frontend now supports fixed-width integer scalar typedef aliases: `int8_t`, `int16_t`, `int32_t`, `int64_t`, `uint8_t`, `uint16_t`, `uint32_t`, and `uint64_t`.
- The exact `signed char` spelling can now enter typed IR as a signed 8-bit integer. Integral promotion casts preserved by clang on ordinary binary operands can emit, for example `signed char value + 1 -> (value as i32) + 1i32`.

These are still **candidate generation** results. They do not mean the real FlashDB slice has `semantic_pass=true`.

## Two Translation Paths

| Path | Code | Current Role |
|------|------|--------------|
| String translator | `crates/c2r-translator/src/lib.rs` | Legacy/demo/bounded fixtures. It should not keep accumulating complex C semantics. The crc32 byte-cursor canned route has been removed, so unmodeled side effects should fail closed. |
| Typed IR translator | `crates/c2r-translator/src/typed_ir.rs` + `clang_frontend.rs` | Current mainline. Real clang AST lowers to a compact skeleton, then typed IR, then the generic emitter produces a Rust candidate. |

Typed IR currently has only two routes:

- `GenericTypedIr`: the generic emitter produced a Rust candidate.
- `Unsupported`: the emitter failed closed, produced no Rust candidate, and preserved route metadata plus the reason.

`GenericTypedIr` answers only whether a Rust draft candidate was generated. It does not decide `semantic_pass`.

## Updated P0 Bottlenecks

### P0.1 The typed IR emitter subset is still too narrow

Important supported increments:

- Scalar declarations, assignments, returns, `if`, and `while`.
- Multi-`VarDecl` declaration statements in ordinary compound bodies and scoped `ForStmt` init slots, for example `int a = 1, b = 2;` and `for (int i = 0, j = 0; i < limit; i++)`.
- Uninitialized scalar local declarations when every later read is proven to occur after assignment, for example `int tmp; tmp = 7; return tmp;`.
- Scalar integer `+ - * / % & | ^ << >>` and signed unary `-`.
- Clang-lowered simple scalar compound assignment family, including narrow clang-proven integer promotion/truncation for simple variable targets.
- Clang-preserved value-position integer implicit casts in declaration initializers, assignment RHS, and return values.
- Comparisons in conditions and narrow value-position C `int` 0/1 materialization.
- Logical not in conditions and narrow value-position C `int` 0/1 materialization.
- Short-circuit `&&` / `||` in conditions plus narrow value-position C `int` 0/1 materialization.
- Pure integer value-position `ConditionalOperator` / `?:` with lazy `IrExpr::Conditional`.
- Narrow `ForStmt` with an explicit typed IR scope, covering simple scalar declaration/assignment init, including multiple simple `VarDecl` declarators, condition, step, and body, emitted as a Rust block plus `while` candidate.
- `break` statements inside `while` / `for` loop bodies.
- Readonly pointer slice parameters, direct `NULL` presence checks, direct readonly `*p` reads, and narrow readonly `*(p+i)` / `*(i+p)` reads.
- Fixed-width integer scalar typedef aliases lowered into typed IR and emitted as Rust `i8` / `i16` / `i32` / `i64` / `u8` / `u16` / `u32` / `u64`; the exact `signed char` spelling also enters the supported integer subset as `i8`.
- Readonly global const integer arrays and local fixed-length integer array reads/writes.
- Bounded direct identifier calls.
- Narrow byte cursor `*p++` prelude support.

Remaining P0 gaps:

- Complete usual scalar conversion classification beyond the current explicit integer-cast and compound-assignment promotion guards.
- Pointer writes, aliasing, and ownership modeling.

### P0.2 clang is no longer "not wired", but AST coverage is still narrow

Real clang smoke tests pass, so the issue is no longer clang installation. The issue is the supported clang skeleton / typed IR subset:

- `CompoundAssignOperator` now lowers for standalone simple scalar variable targets, including clang-proven integer promotion/truncation when target/result match, compute lhs/result match, and all involved types are supported integers.
- `&&` / `||` now lower for condition positions and narrow value positions; return values, assignment RHS, and declaration initializers are covered.
- `DeclStmt` nodes in ordinary compound bodies and `ForStmt` init slots now expand multiple simple `VarDecl` children in source order.
- Scalar local declarations without initializers now emit through the generic typed IR route when the conservative assignment-before-read guard proves every read is initialized.
- Ordinary `ConditionalOperator` now lowers for pure integer value positions only; GNU `BinaryConditionalOperator` still fails closed.
- `ForStmt` now has narrow scoped lowering: init accepts only simple scalar `DeclStmt`, including multiple simple `VarDecl` declarators, or assignment; condition reuses the current condition emitter, step accepts only simple assignment/compound assignment/postfix inc-dec, body reuses the existing statement subset, and loop-body `break` is supported. `continue` / `goto` / `switch`, condition variable slots, empty condition/step, and complex init/step remain fail-closed.
- `Deref(Binary(Add, p, i))` is now normalized into a bounded slice index when the base is a readonly integer pointer and the index is a side-effect-free integer expression; other pointer arithmetic remains unmodeled.
- `type_from_qual_type()` now recognizes fixed-width integer typedef aliases plus exact `signed char`, while other target-dependent spellings such as `short` / `long long`, plain `char`, plain `long`, and complete usual scalar conversions remain closed.
- Structs/records, field access, switch/goto/do-while, and memory semantics are still outside the safe emitter.

## Recommended Route

The right next path is not returning to FlashDB-specific templates. Continue extending typed IR through small verifiable slices:

1. **Usual conversions classification**: continue turning provable integral-cast and compute-type rules into explicit guards instead of claiming full C conversions.
2. **Struct / memory model design**: flat structs, field access, pointer writes, aliasing, and ownership need a separate design plus validation gates.
3. **Wider control flow**: after the scoped `ForStmt` MVP and loop-body `break`, design explicit semantics and validation boundaries for `continue` / `do-while` / `switch` / `goto`.

## Boundaries

These should still fail closed:

- Arbitrary pointer comparison, pointer truthiness, and nullable pointer index/deref after a null check.
- Target-dependent spellings such as `short` / `long long`, plain `char`, plain `long`, target-ABI width inference, and complete integer promotion/usual scalar conversions. The exact `signed char` spelling is open only as a signed 8-bit integer slice.
- Pointer arithmetic other than the narrow readonly integer pointer plus side-effect-free integer index `*(p+i)` read.
- Condition-position `?:`, expression-statement `?:`, GNU omitted-middle `a ?: b`, and conditional branches with call/inc/dec/post-increment/assignment/comma side effects.
- Short-circuit operands containing calls/inc/dec/side effects, pointer truthiness, floating-point truthiness, unsupported types, or cases requiring full usual scalar conversions.
- Compound assignments with non-simple targets, value-position use, unsupported compute/result type combinations, pointer arithmetic, floating-point, volatile, or complex RHS side effects.
- `ForStmt` with `continue` / `goto` / `switch`, a condition variable slot, empty condition/step, calls/inc/dec/side effects in the condition, complex init/step, non-simple-scalar init/step, or prefix inc-dec in the step. `break` is open only as direct loop-exit candidate generation inside loop bodies.
- Unsupported type/initializer in any `ForStmt` init declarator, VLA/incomplete arrays, and duplicate symbols.
- Uninitialized local reads before assignment, first assignments that read the same variable, initialization through only one branch or only a loop body, address-taken initialization, indirect writes, and alias writes.
- Mutable pointers, pointer writes, and unmodeled alias writes.
- Function-pointer callees, complex call side effects, and nested calls in conditions.
- Volatile, hardware registers, cross-thread, and interrupt semantics.
- Unmodeled macro side effects, unrecoverable control flow, and insufficient test oracles.
- Semantic acceptance not proven by the full C/Rust oracle, negative diff, unsafe ledger, and final verification pipeline.

## Conclusion

The proposal direction is right: **the validation gates are strict enough; the core work is extending the typed IR translator.**

The P0 wording should be updated: the task is no longer "install clang / make pointer stop failing", and `*(p+i)` is no longer completely missing. It is now "continue extending the provable generic typed IR subset on top of a working real-clang path". FlashDB remains an important use case and gate sample, but the project should not become a FlashDB-specific translator.
