英文镜像见 `checklist.en.md`。

# Pointer Dependency Graph Checklist

Use this checklist before translating a pointer-bearing C slice or reporting L2/L3 success for one.

## Applicability

- [ ] Slice id and target id are recorded.
- [ ] Source commit and repo commit are recorded.
- [ ] ContextPack reference is recorded.
- [ ] Impact set and config profile references are recorded when available.
- [ ] Pointer graph status is `recorded`, `not_applicable` with a non-empty reason, or `not_evaluated` with a non-empty reason when translation was blocked before pointer analysis ran.
- [ ] Applicability decision covers pointer parameters, pointer returns, struct pointer fields, buffers, callbacks, opaque handles, globals, manual allocation, and external mutable state.

## Graph Content

- [ ] C files, functions, structs, fields, globals, callbacks, and direct call edges are listed.
- [ ] Pointer nodes include type, kind, mutability, nullability, ownership role, lifetime owner, and cross-file exposure.
- [ ] Pointer nodes record read effects and write effects when the slice reads or writes through pointers.
- [ ] Dependency edges include relationship type and evidence source.
- [ ] Aliasing or ownership equivalence classes are recorded when known.
- [ ] Alias-sensitive read/write combinations record `alias_contract`, `alias_risks`, `alias_sets`, and `safe_boundary_preconditions`.
- [ ] Newly generated `schema_version=2` pointer graphs record `effect_graph`; alias-sensitive read/write graphs include read effects, write effects, and matching `requires_noalias` or `may_alias` edges for each alias risk.
- [ ] External mutable state and side effects are recorded.
- [ ] Unknown or unverified relationships are listed as assumptions or gaps.

中文检查：如果 slice 同时有指针读和指针写，必须能看出 alias 风险、noalias 前置条件、`effect_graph` 里的读写 effect、风险边和最终 gate decision；不能只在 `known_gaps` 里用自然语言带过。

## Rust Mapping

- [ ] Each important pointer node has a Rust mapping strategy.
- [ ] The graph records whether the mapping expects safe Rust, bounded unsafe, or a blocked design decision.
- [ ] Any expected unsafe is linked to the unsafe ledger requirement.
- [ ] Public API, FFI, and callback boundaries are marked separately.

## Validation

- [ ] Tests, fixtures, C oracle evidence, or differential evidence cover the pointer risk boundary.
- [ ] Cache invalidation keys include source commit, source file hashes, function boundary, ContextPack reference, graph schema version, config profile, fixture hash, and Rust mapping strategy.
- [ ] Graph changes invalidate ContextPack, PatchPlan, C oracle, Rust replay, diff, unsafe ledger, performance smoke, and summary evidence.
- [ ] The summary does not claim full alias safety or whole-program pointer coverage.
