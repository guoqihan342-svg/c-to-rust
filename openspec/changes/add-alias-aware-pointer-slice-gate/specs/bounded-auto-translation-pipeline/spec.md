## ADDED Requirements

### Requirement: Alias-Aware Pointer Gate Integration
The system SHALL integrate alias risk evidence into bounded auto-translation runs before accepting pointer-bearing safe Rust public boundaries.

系统必须在接收含指针 slice 的 safe Rust public boundary 前，把 alias 风险证据纳入自动翻译运行。

#### Scenario: Pointer graph records alias gate output
- **WHEN** an automatic translation run emits `l3-<slice>-pointer-graph.json` for a slice with at least one pointer read and one pointer write
- **THEN** the pointer graph records `alias_sets`, `alias_risks`, `alias_contract`, and `safe_boundary_preconditions`
- **AND** every risk item records pointer node ids, risk level, evidence source, gate decision, and whether noalias is required

#### Scenario: Unknown alias cannot be accepted as alias-safe
- **WHEN** a pointer-bearing slice has input/output pointers whose overlap cannot be proven impossible
- **THEN** the auto-translation plan records an alias gate decision of `requires_noalias_contract`, `candidate_only`, or `blocked`
- **AND** final verification does not claim complete alias safety
- **AND** the manifest records the alias gate status before semantic acceptance

#### Scenario: Alias gate participates in cache invalidation
- **WHEN** alias sets, pointer roles, source read/write effects, fixture overlap policy, noalias assumptions, or Rust boundary strategy change
- **THEN** cached context pack, pointer graph, Rust draft, C oracle, Rust replay, diff, unsafe ledger, and final summary are invalidated or explicitly reviewed

#### Scenario: Missing alias evidence fails pointer-bearing acceptance
- **WHEN** a pointer-bearing slice has both read effects and write effects but its pointer graph lacks alias gate fields
- **THEN** the validator fails the automatic translation evidence package
- **AND** it reports the missing alias gate fields instead of silently accepting the manifest
