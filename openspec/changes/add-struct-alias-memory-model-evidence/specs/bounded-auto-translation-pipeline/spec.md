## ADDED Requirements

### Requirement: Struct And Alias Memory Model Evidence
The system SHALL expose pointer, alias, ownership, length, and memory-effect contracts in reusable bounded auto-translation templates before accepting alias-sensitive C-to-Rust candidates.

系统必须在可复用的有界自动翻译模板中暴露 pointer、alias、ownership、length 和 memory-effect 契约，然后才能接受 alias-sensitive 的 C-to-Rust 候选结果。

#### Scenario: Slice spec records pointer contract input
- **WHEN** a slice contains pointer reads, pointer writes, struct pointer fields, callbacks, or external mutable state that affect the Rust boundary
- **THEN** the slice spec records `c_boundary.pointer_contract`
- **AND** the pointer contract records input buffers, output pointers, inout pointers, length companions, read effects, write effects, aliasing proof status, read-read alias allowances, and required noalias pairs

#### Scenario: Slice spec records memory model assumptions
- **WHEN** the Rust boundary depends on pointer aliasing, ownership, length companions, or memory effects
- **THEN** the slice spec records `memory_model`
- **AND** the memory model records `alias_contract`, `ownership_contract`, `length_companions`, and `effect_graph`

#### Scenario: Pointer graph records alias and effect evidence
- **WHEN** the pipeline emits pointer graph evidence for a pointer-bearing slice
- **THEN** the pointer graph schema supports `alias_contract`, `alias_risks`, `alias_sets`, `safe_boundary_preconditions`, `effect_graph`, and pointer-node read/write effects
- **AND** alias-sensitive read/write combinations do not rely only on natural-language non-goals

#### Scenario: Alias gate propagates to claim boundaries
- **WHEN** a pointer graph records alias-sensitive read/write effects
- **THEN** the auto-translation plan records `translation_summary.alias_gate`
- **AND** the L3 evidence manifest records `claim_boundary.alias_gate`
- **AND** final acceptance remains bounded by C oracle, Rust replay, schema-aware diff, negative diff, unsafe evidence, cache/version binding, and final verification

#### Scenario: Historical evidence remains compatible while new templates are explicit
- **WHEN** historical evidence predates the alias/memory-model fields
- **THEN** schema additions remain additive unless a validator is checking a newly generated alias-sensitive evidence package
- **AND** newly generated alias-sensitive packages fail closed when required alias-gate evidence is missing
