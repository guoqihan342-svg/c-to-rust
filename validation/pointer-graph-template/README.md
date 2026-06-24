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
- `pointer-graph.example.json`: FlashDB-style example graph for a KVDB visible-behavior slice.
- `checklist.md`: review checklist before translation or L3 reporting.
