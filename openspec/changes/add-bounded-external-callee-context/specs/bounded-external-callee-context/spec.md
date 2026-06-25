## ADDED Requirements

### Requirement: Declared External Direct Callee Context
The system SHALL support a bounded external direct callee only when the slice spec explicitly declares the callee signature and source boundary.

系统必须仅在 slice spec 显式声明 callee signature 和 source boundary 时，才支持 bounded external direct callee。

#### Scenario: Declared helper callee is accepted as compile context
- **WHEN** a slice contains `helper(value)` in a bounded direct call expression
- **AND** the slice spec declares `helper` in `c_boundary.signatures[]` with a supported primitive signature
- **THEN** the automatic translation run records the helper as declared external callee context
- **AND** the generated Rust draft may include a compile-only Rust helper stub for rust-check

#### Scenario: Undeclared helper callee is blocked
- **WHEN** a slice contains `helper(value)` in a bounded direct call expression
- **AND** the slice spec does not declare `helper` as a callee boundary
- **THEN** the automatic translation run MUST NOT silently inject a helper stub
- **AND** the run records an unsupported or blocked callee context reason

### Requirement: Compile-Only Callee Stub Boundary
The system SHALL distinguish compile-only callee stubs from semantic evidence.

系统必须区分 compile-only callee stub 与语义正确性证据。

#### Scenario: Helper stub does not claim semantic equivalence
- **WHEN** auto_migrate injects a Rust helper stub for a declared external callee
- **THEN** context pack and final manifest record `stub_kind: "compile_only"`
- **AND** they record `semantics_verified: false`
- **AND** `generated_draft_semantic_pass` remains false unless a later gate explicitly validates that exact generated draft

#### Scenario: Accepted semantics still come from L3 evidence
- **WHEN** an external-callee demo slice reaches semantic pass
- **THEN** the pass is bound to accepted C oracle, Rust replay, schema diff, negative diff, unsafe, final verification, and version evidence
- **AND** the compile-only helper stub is not used as correctness evidence

### Requirement: External Callee L3 Demo Slice
The system SHALL provide a `demo-external-direct-callee` L3 slice that validates declared external helper call context through the existing evidence gates.

系统必须提供 `demo-external-direct-callee` L3 slice，通过现有 evidence gate 验证声明式 external helper call context。

#### Scenario: Oracle and replay cover helper call contexts
- **WHEN** the `call_helper_chain` C oracle runs over the committed fixture corpus
- **THEN** it records declaration initializer, assignment RHS, and return expression helper call contexts
- **AND** Rust replay records matching observable outputs and helper call metadata

#### Scenario: Auto evidence preserves helper callee context
- **WHEN** `auto_migrate --accept-existing-evidence` runs for `demo-external-direct-callee`
- **THEN** the normalized plan records bounded direct call expression evidence for the helper callee
- **AND** the context pack records direct call edges and external callee metadata
- **AND** the semantic manifest records compile-only stub boundary without claiming helper stub semantics
