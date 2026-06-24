## ADDED Requirements

### Requirement: Pointer dependency graph template
The system SHALL provide a reusable pointer dependency graph template for bounded C-to-Rust migration slices.

中文：系统必须为有边界的 C-to-Rust 迁移切片提供可复用 pointer dependency graph 模板。

#### Scenario: Template files are present
- **WHEN** an agent prepares a pointer-bearing migration slice
- **THEN** it can read `validation/pointer-graph-template/README.md`
- **AND** it can read `validation/pointer-graph-template/checklist.md`
- **AND** it can read `validation/pointer-graph-template/pointer-graph.schema.json`
- **AND** it can read `validation/pointer-graph-template/pointer-graph.example.json`

### Requirement: Pointer-bearing slices require graph evidence
The system SHALL require pointer dependency graph evidence before translating or reporting L2/L3 success for pointer-bearing C slices.

中文：对于含指针的 C 切片，系统必须在翻译或报告 L2/L3 成功前要求 pointer dependency graph 证据。

#### Scenario: Pointer-bearing slice starts
- **WHEN** a selected C slice contains pointer parameters, pointer returns, struct pointer fields, buffers, external mutable state, callbacks, opaque handles, manual allocation, or alias-sensitive state
- **THEN** the agent records pointer dependency graph evidence before implementation edits
- **AND** the graph records ContextPack reference, pointer nodes, dependency edges, ownership and lifetime assumptions, external state, Rust mapping strategy, tests or fixtures, and cache invalidation keys

### Requirement: Pure value slices explicitly opt out
The system SHALL allow pure value slices to mark pointer graph evidence as `not_applicable` only with a recorded reason.

中文：纯值切片只有在写明原因时，才能把 pointer graph 证据标记为 `not_applicable`。

#### Scenario: Pure value slice has no pointer surface
- **WHEN** a selected slice has no C pointer parameters, pointer returns, pointer fields, external mutable state, callback context, or alias-sensitive buffers
- **THEN** the pointer graph evidence records `status:"not_applicable"`
- **AND** it records a non-empty `not_applicable_reason`

### Requirement: Pointer graph is not an alias proof
The system SHALL state that pointer dependency graph evidence is a context and risk-boundary artifact, not a proof of complete alias safety.

中文：系统必须说明 pointer dependency graph 是上下文与风险边界证据，而不是完整 alias 安全证明。

#### Scenario: Agent reports a pointer-bearing L3 pass
- **WHEN** an agent reports L3 semantic-equivalence evidence for a pointer-bearing slice
- **THEN** the report may cite the pointer graph as dependency evidence
- **AND** it must not claim complete alias safety, whole-program pointer coverage, or safe Rust proof unless separately verified

### Requirement: Pointer graph drift invalidates reusable evidence
The system SHALL treat pointer graph drift as invalidating affected context, patch, diff, unsafe, and summary evidence.

中文：当 pointer graph 漂移时，系统必须把受影响的 context、patch、diff、unsafe 和 summary 证据视为失效。

#### Scenario: Pointer graph inputs change
- **WHEN** source commit, source file hash, config profile, function boundary, pointer node, dependency edge, ownership assumption, Rust mapping strategy, fixture, or toolchain context changes
- **THEN** cached ContextPack, PatchPlan suggestions, C oracle evidence, Rust replay evidence, diff conclusions, unsafe ledger, performance smoke, and summary claims must be regenerated or explicitly invalidated
