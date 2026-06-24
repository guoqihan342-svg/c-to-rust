## Why

The current migration gates record slice scope, context packs, unsafe ledgers, and config profiles, but they do not force an explicit pointer dependency view before translating pointer-heavy C slices. This leaves a known risk from C-to-Rust research: a narrow function slice can look safe while hidden aliasing, ownership, external-state, or lifetime relationships propagate across files.

中文：当前门禁已经记录切片范围、ContextPack、unsafe ledger 和 config profile，但在翻译含指针 C 切片前，还没有强制生成显式 pointer dependency view。这会留下一个已知风险：函数级切片看起来很小，但隐藏的 aliasing、ownership、外部状态或生命周期关系可能跨文件传播。

## What Changes

- Add a reusable pointer dependency graph template under `validation/pointer-graph-template/`.
- Define a small JSON schema and example that records pointer nodes, dependency edges, ownership/lifetime assumptions, external mutable state, Rust mapping strategy, and invalidation keys.
- Update L2 and L3 validation gates so pointer-bearing slices require pointer graph evidence before translation or semantic-equivalence claims.
- Link pointer graph evidence from the L3 template as a conditional required artifact: pointer-heavy slices must provide it; pure value slices may record `not_applicable` with a reason.
- Keep the scope lightweight: no full alias-analysis engine, no symbolic proof, no whole-program pointer solver, and no runtime code changes.

## Capabilities

### New Capabilities

- `pointer-dependency-graph-gate`: Defines the conditional pointer dependency graph evidence required before translating or validating pointer-bearing C-to-Rust slices.

### Modified Capabilities

- `l3-validation-template`: Adds pointer dependency graph evidence references to the existing reusable L3 evidence package.

## Impact

- Affected docs/templates: `validation/pointer-graph-template/`, `validation/l3-template/`, `validation/gates.md`, `validation/README.md`.
- Affected OpenSpec artifacts: new capability spec plus a delta for the L3 template.
- No Rust runtime behavior changes.
- No new dependencies.
- Historical FlashDB evidence remains historical evidence; future pointer-bearing L2/L3 slices must provide pointer graph evidence or explicitly mark the graph as not applicable.
