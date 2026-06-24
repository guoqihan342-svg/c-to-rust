## ADDED Requirements

### Requirement: L3 pointer dependency graph reference
The L3 validation template SHALL reference pointer dependency graph evidence for future L3 slices.

中文：L3 验证模板必须为后续 L3 切片引用 pointer dependency graph 证据。

#### Scenario: L3 manifest references pointer graph evidence
- **WHEN** a future L3 evidence manifest is prepared
- **THEN** it includes `evidence.pointer_dependency_graph`
- **AND** the referenced artifact has status `recorded` for pointer-bearing slices or `not_applicable` with a reason for pure value slices
- **AND** recorded graph evidence includes a ContextPack reference, source boundary, pointer nodes, dependency edges, ownership and lifetime assumptions, external state, Rust mapping strategy, tests or fixtures, config/profile identity, and cache invalidation keys

### Requirement: Pointer graph does not replace semantic diff
The L3 validation template SHALL keep pointer graph evidence separate from C/Rust semantic-equivalence evidence.

中文：L3 验证模板必须把 pointer graph 证据与 C/Rust 语义等价证据分开。

#### Scenario: Pointer graph exists but diff is missing
- **WHEN** pointer graph evidence exists but C oracle, Rust replay, schema diff, or negative diff evidence is missing
- **THEN** the L3 claim remains incomplete
