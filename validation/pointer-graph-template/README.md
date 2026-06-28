英文镜像见 `README.en.md`。

# Pointer Dependency Graph Template

This template defines the minimum pointer dependency evidence for bounded C-to-Rust migration slices. Use it before translating any slice that contains C pointers, buffers, opaque handles, callbacks, manual allocation, external mutable state, or alias-sensitive structs.

中文：本模板定义有边界 C-to-Rust 迁移切片的最小指针依赖证据。任何切片只要包含 C 指针、buffer、opaque handle、callback、手动分配、外部可变状态或 alias-sensitive struct，都应在翻译前使用它。

## Purpose

Pointer graph evidence preserves cross-file pointer context before Rust mapping decisions are made. It helps the agent avoid treating a local function as isolated when its correctness depends on aliases, ownership, lifetime, external state, callbacks, or mutation through another path.

The graph is evidence, not proof. It does not prove whole-program alias safety, safe Rust soundness, or complete branch coverage. L2 and L3 still require compilation, unsafe ledger, C/Rust differential evidence, negative diff, and final verification where applicable.

## Required Evidence

Every pointer graph artifact should record:

- slice identity: target id, slice id, source commit, repo commit, and level.
- trigger: why a graph is required or why it is `not_applicable`.
- source boundary: C files, functions, structs, fields, globals, callbacks, and relevant call edges.
- evidence links: ContextPack reference, optional impact-set reference, and optional config-profile reference.
- pointer nodes: handles, owner pointers, borrowed views, buffers, struct fields, globals, callbacks, and derived pointers.
- dependency edges: owns, borrows, aliases, derives-from, stores, returns, passes-to, reads-through, writes-through, invalidates, and callback-captures relationships.
- ownership and lifetime assumptions.
- external mutable state and side effects.
- Rust mapping strategy and unsafe expectation.
- tests, fixtures, or oracle evidence that cover the risk boundary.
- cache invalidation keys.

## Alias And Effect Gate

English: pointer-bearing slices must distinguish pointer topology from memory effects. `pointer_nodes[*].read_effects` and `pointer_nodes[*].write_effects` record the local read/write surface. `effect_graph` records the structured effect nodes and data/control/alias relationships. When a slice has both read and write pointer effects and aliasing is not proven, the artifact must record `alias_contract`, `alias_risks`, `alias_sets`, and `safe_boundary_preconditions`.

中文：含指针的 slice 不能只记录“有哪些指针”，还要记录“这些指针读写了什么”。`pointer_nodes[*].read_effects` 和 `pointer_nodes[*].write_effects` 描述局部读写面；`effect_graph` 描述结构化 effect 节点以及数据、控制、别名关系。当同一个 slice 同时存在指针读和指针写，并且无法证明 noalias 时，必须记录 `alias_contract`、`alias_risks`、`alias_sets` 和 `safe_boundary_preconditions`。

English: newly generated pointer graph artifacts use `schema_version=2`. For v2 alias-sensitive read/write pointer graphs, `effect_graph` is required and must include read effects, write effects, and alias-risk edges such as `requires_noalias` or `may_alias`. Historical v1 artifacts may omit this field, but they must not be treated as the current generated format.

中文：新生成的 pointer graph artifact 使用 `schema_version=2`。v2 的 alias-sensitive 指针读写图必须包含 `effect_graph`，并记录 read effects、write effects，以及 `requires_noalias` 或 `may_alias` 等 alias-risk 边。历史 v1 artifact 可以缺少该字段，但不能被当作当前生成格式。

English: this is still evidence, not a whole-program alias solver. `complete_alias_safety=false` is expected unless a later proof or gate can justify a stronger claim.

中文：这些字段仍然是证据契约，不是全程序 alias 求解器。除非后续有更强证明或门禁，默认应保持 `complete_alias_safety=false`，不能声称完整 alias safety。

## Status Rules

- `recorded`: graph evidence exists for a pointer-bearing slice.
- `not_applicable`: the slice has no pointer surface and the artifact records a non-empty reason.
- `stale`: graph inputs changed and evidence must be regenerated before reuse.
- `incomplete`: required graph fields are missing.

## Non-Goals

- No whole-program pointer solver.
- No symbolic alias proof.
- No guarantee that safe Rust is possible.
- No replacement for unsafe ledger, C oracle, Rust replay, schema diff, or negative diff.
- No claim about async, multithreaded, interrupt, or runtime cache semantics unless separately proven.

## Files

- `pointer-graph.schema.json`: schema for pointer graph evidence.
- `pointer-graph.example.json`: schema v2 FlashDB-style example graph for a KVDB visible-behavior slice.
- `checklist.md`: review checklist before translation or L3 reporting.
