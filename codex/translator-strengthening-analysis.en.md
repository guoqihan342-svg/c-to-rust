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
- Scalar integer `+ - * / % & | ^ << >>` and signed unary `-`.
- Comparisons in conditions and narrow value-position C `int` 0/1 materialization.
- Logical not in conditions and narrow value-position C `int` 0/1 materialization.
- Readonly pointer slice parameters, direct `NULL` presence checks, direct readonly `*p` reads, and narrow readonly `*(p+i)` / `*(i+p)` reads.
- Readonly global const integer arrays and local fixed-length integer array reads/writes.
- Bounded direct identifier calls.
- Narrow byte cursor `*p++` prelude support.

Remaining P0 gaps:

- First-class typed IR compound assignment such as `x += y`.
- Short-circuit `&&` / `||`.
- Complete usual scalar conversion classification.
- Pointer writes, aliasing, and ownership modeling.

### P0.2 clang is no longer "not wired", but AST coverage is still narrow

Real clang smoke tests pass, so the issue is no longer clang installation. The issue is the supported clang skeleton / typed IR subset:

- `CompoundAssignOperator` is not yet modeled as typed IR.
- `&&` / `||` are not yet mapped into typed IR.
- `Deref(Binary(Add, p, i))` is now normalized into a bounded slice index when the base is a readonly integer pointer and the index is a side-effect-free integer expression; other pointer arithmetic remains unmodeled.
- Structs/records, field access, switch/goto/do-while, and memory semantics are still outside the safe emitter.

## Recommended Route

The right next path is not returning to FlashDB-specific templates. Continue extending typed IR through small verifiable slices:

1. **Bounded readonly offset-deref hardening**: `*p -> p[0usize]` and narrow `*(p+i)` / `*(i+p) -> p[i as usize]` now work; the next step is keeping real-clang, documentation, and fail-closed boundary coverage in place.
2. **Scalar compound assignment**: add a first-class typed IR statement, initially only for scalar `Var` targets, rejecting indexed or side-effecting lvalues.
3. **Condition-position `&&` / `||`**: only allow side-effect-free comparison/logical-not operands and preserve short-circuit behavior. Value-position 0/1 materialization should be separate.
4. **Usual conversions classification**: turn the provable integral-cast rules into explicit guards instead of claiming full C conversions.
5. **Struct / memory model design**: flat structs, field access, pointer writes, aliasing, and ownership need a separate design plus validation gates.

## Boundaries

These should still fail closed:

- Arbitrary pointer comparison, pointer truthiness, and nullable pointer index/deref after a null check.
- Pointer arithmetic other than the narrow readonly integer pointer plus side-effect-free integer index `*(p+i)` read.
- Mutable pointers, pointer writes, and unmodeled alias writes.
- Function-pointer callees, complex call side effects, and nested calls in conditions.
- Volatile, hardware registers, cross-thread, and interrupt semantics.
- Unmodeled macro side effects, unrecoverable control flow, and insufficient test oracles.
- Semantic acceptance not proven by the full C/Rust oracle, negative diff, unsafe ledger, and final verification pipeline.

## Conclusion

The proposal direction is right: **the validation gates are strict enough; the core work is extending the typed IR translator.**

The P0 wording should be updated: the task is no longer "install clang / make pointer stop failing", and `*(p+i)` is no longer completely missing. It is now "continue extending the provable generic typed IR subset on top of a working real-clang path". FlashDB remains an important use case and gate sample, but the project should not become a FlashDB-specific translator.
