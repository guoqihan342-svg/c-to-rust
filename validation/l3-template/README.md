英文镜像见 `README.en.md`。

# L3 Validation Template

This template defines the minimum evidence package for a bounded C-to-Rust L3 migration slice. It is based on the existing FlashDB L3 evidence chain and is intended for FlashDB and future, larger C projects.

此模板定义有边界 C-to-Rust L3 迁移切片的最小证据包。它提炼自现有 FlashDB L3 验证链，可供 FlashDB 和未来更复杂的 C 项目复用。

## Purpose

L3 is the first level that can support a limited semantic-equivalence claim. The claim is valid only for the named slice, pinned source commit, fixture input domain, and behavior fields checked by C/Rust differential evidence.

L3 是第一个可以支持有限语义等价声明的层级。该声明只适用于命名切片、固定 source commit、fixture 输入域，以及 C/Rust 差分证据实际检查过的行为字段。

## Required Evidence

Every L3 slice must provide:

- slice contract: selected C/Rust boundary, APIs, fixture, non-goals, and accepted differences.
- context pack: direct modules, callers/callees, tests, unsafe status, rollback/cache/version facts.
- config profile: normalized C config header hash, `#define` values, feature matrix, compile/include profile, Rust Cargo features, Rust feature environment, backend profile, and cache invalidation keys.
- pointer dependency graph: C pointer nodes, dependency edges, ownership/lifetime assumptions, external mutable state, Rust mapping strategy, and invalidation keys for pointer-bearing slices; pure value slices record `not_applicable` with a reason.
- test translation: source C tests, fixtures, or oracle expectations mapped to Rust test files, Rust test names, cargo commands, main/error path coverage, negative cases, evidence links, known gaps, and cache invalidation keys.
- C oracle report: generated from pinned C source and the same fixture input.
- Rust replay report: generated from the migrated Rust implementation and the same fixture input.
- schema-aware diff: compares behavior fields and records `first_mismatch`.
- negative diff: mutates behavior evidence and proves the diff gate rejects it.
- rust check: compile/test status and self-healing attempt count.
- unsafe evidence: unsafe scan and ledger, even when unsafe count is zero.
- performance smoke: secondary-only timing or operation-count evidence.
- final verification: final command evidence before reporting, archiving, commit, or push.
- summary: machine-readable L3 claim, known gaps, evidence paths, and next-slice guidance.
- version or configuration binding: source commit, fixture hash, toolchain/version manifest, feature matrix, macro/config profile, and cache key facts.
- for automatic-translation L3 evidence: C2Rust baseline manifest, route decision, and validation profile are required first-class artifacts. The baseline is candidate context only; the route selects the candidate path; the validation profile defines the required gates.

## Config Profile Gate

The config profile is an identity and invalidation gate. It proves that all L3 evidence for the slice is tied to the same C config header, macro/feature matrix, compile profile, Rust Cargo features, Rust feature environment, backend profile, fixture, and toolchain inputs.

It is not a macro solver. It does not prove every possible `#ifdef` branch, every macro expansion, or every build profile was explored. If any profile input changes, affected C oracle, Rust replay, diff, unsafe, performance, cache, and summary evidence must be regenerated or explicitly invalidated.

中文：config profile 是证据身份与缓存失效门禁，用于证明该切片的 L3 证据绑定到同一组 C 配置头、宏/feature 矩阵、编译 profile、Rust Cargo features、Rust feature environment、backend、fixture 和工具链输入。它不是完整宏求解器，也不证明所有 `#ifdef` 分支、宏展开或构建 profile 都已覆盖。任一 profile 输入变化时，受影响的 C oracle、Rust replay、diff、unsafe、performance、cache 和 summary 证据必须重新生成或显式标记失效。

## Pointer Dependency Graph Gate

Pointer dependency graph evidence is required for future L3 slices that carry C pointer parameters, pointer returns, struct pointer fields, buffers, opaque handles, callbacks, manual allocation, external mutable state, or alias-sensitive state. It is recorded before implementation edits so Rust ownership and unsafe decisions are made with the cross-file pointer context visible.

The pointer graph is not an alias proof. It does not prove whole-program pointer coverage or safe Rust soundness. It records dependency context, risk boundaries, and cache invalidation inputs.

中文：后续 L3 切片只要包含 C 指针参数、指针返回、struct 指针字段、buffer、opaque handle、callback、手动分配、外部可变状态或 alias-sensitive state，就必须提供 pointer dependency graph 证据。该图应在实现编辑前记录，确保 Rust ownership 与 unsafe 决策能看到跨文件指针上下文。它不是 alias 证明，只是依赖上下文、风险边界和缓存失效输入。

## Alias Gate Claim Boundary

English: automatic-translation L3 manifests must carry `claim_boundary.alias_gate` when the pointer graph records alias-sensitive read/write effects. The field mirrors the pointer graph and translation plan decision so the final claim can say exactly whether alias safety is proven, candidate-only, blocked, or dependent on explicit noalias preconditions.

中文：当 pointer graph 记录了 alias-sensitive 的读写 effect 时，自动翻译的 L3 manifest 必须带 `claim_boundary.alias_gate`。该字段承接 pointer graph 和 translation plan 的决策，让最终声明能明确说明 alias safety 是已证明、仅候选、被阻断，还是依赖显式 noalias 前置条件。

English: FlashDB is only one validation use case. The alias gate applies to any C project where pointer reads, pointer writes, struct fields, callbacks, or external mutable state affect the Rust boundary.

中文：FlashDB 只是验证用例之一。只要 C 项目的指针读、指针写、结构体字段、callback 或外部可变状态会影响 Rust 边界，就应该使用 alias gate。

## Code-Test Translation Gate

Code-test translation evidence is required for future L3 slices. It records how source-side tests, generated fixtures, or oracle expectations map to Rust tests and replay commands. A generated oracle fixture is a valid source mapping when no direct upstream C test name exists.

This evidence is not a semantic-equivalence proof. If C oracle, Rust replay, schema diff, or negative diff evidence is missing or stale, the L3 claim remains incomplete even when test translation evidence is present.

中文：code-test translation evidence 用于证明测试映射可追溯，而不是证明完整语义等价。没有直接上游 C test 名称时，可以用生成的 oracle fixture 或 oracle expectation 作为 source mapping；但它不能替代 C oracle、Rust replay、schema diff 或 negative diff。

## Pass Semantics

An L3 slice is incomplete when any required evidence is missing, stale, skipped without replacement evidence, or only indirectly implied.

The C oracle must be generated by a real C toolchain. A local Windows `SKIPPED_LOCAL_NO_C_TOOLCHAIN` marker is useful evidence, but it is not a pass. The pass must come from WSL/Linux/CI evidence with `C_ORACLE_GENERATED` or an equivalent explicit marker.

The schema-aware diff must pass with no behavior-field mismatch. Accepted differences are limited to explicitly listed metadata fields such as backend, report path, image hash, toolchain status, source metadata, fixture metadata, or other non-behavior fields.

Performance smoke never replaces correctness. It is recorded only after the semantic gate has evidence.

For legacy accepted auto-translation fixtures, compatibility only means older route/profile payloads may omit optional candidate-generation details. It does not allow a semantic-pass manifest to omit `c2rust_baseline`, `route_decision`, or `validation_profile` refs, nor to omit schema-aware diff and negative-diff gate metadata.

中文：历史 fixture 的兼容性只针对字段形状，不等于可以缺少三件套证据。只要要通过当前 `--require-semantic-pass`，L3 manifest、auto manifest、final verification、cache metadata 都必须绑定同一组 baseline/route/profile refs，并且 diff/negative-diff 必须带 schema-aware gate 元数据。

## Existing FlashDB Examples

Representative slices:

- `kvdb-lifecycle`: `validation/evidence/flashdb/l3-kvdb-lifecycle-summary.json`
- `kvdb-compact-overwrite`: `validation/evidence/flashdb/l3-kvdb-compact-overwrite-summary.json`
- `tsdb-user2-status`: `validation/evidence/flashdb/l3-tsdb-user2-status-summary.json`

Useful shared evidence:

- `validation/evidence/flashdb/version-governance-manifest.json`
- `validation/evidence/flashdb/version-governance-summary.json`

Machine-readable template files:

- `validation/l3-template/evidence-manifest.json`: canonical required/optional evidence categories.
- `validation/l3-template/evidence-manifest.schema.json`: schema for future per-slice L3 evidence manifests.
- `validation/l3-template/evidence-manifest.example.json`: example per-slice manifest using `kvdb-compact-overwrite`.
- `validation/l3-template/config-profile.schema.json`: schema for future config-profile evidence.
- `validation/l3-template/config-profile.example.json`: example config profile using the current FlashDB oracle config.
- `validation/pointer-graph-template/`: schema, checklist, and example for pointer dependency graph evidence.
- `validation/test-translation-template/`: schema, checklist, and example for code-test translation evidence.

## Non-Goal Language

Every L3 summary must explicitly state what it does not prove. Common non-goals:

- full project migration.
- byte-for-byte flash image equivalence.
- GC, sector rollover, native sector layout, wear, or capacity-pressure behavior.
- power-loss recovery unless separately tested.
- unrelated KVDB/TSDB slices.
- async, multithreaded, or runtime-cache semantics unless separately designed and proven.

## Future Validator

`evidence-manifest.json` is intentionally machine-readable so a later change can add a validator without changing the template shape.
