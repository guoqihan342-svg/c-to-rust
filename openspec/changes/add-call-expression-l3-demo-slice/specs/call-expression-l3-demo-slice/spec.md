## ADDED Requirements

### Requirement: Call Expression L3 Demo Slice
The system SHALL provide a `demo-call-expression` L3 slice that validates bounded direct call expression evidence through the C oracle, Rust replay, diff, negative diff, unsafe, and auto evidence gates.

系统必须提供 `demo-call-expression` L3 slice，通过 C oracle、Rust replay、diff、negative diff、unsafe 和 auto evidence gate 验证 bounded direct call expression evidence。

#### Scenario: Oracle and replay cover call expression contexts
- **WHEN** the `call_expression_chain` C oracle runs over the committed fixture corpus
- **THEN** it records accepted cases for declaration initializer call, assignment call, and return call contexts
- **AND** the Rust replay records matching return values and call expression metadata for the same cases

#### Scenario: Diff and negative diff detect call expression regressions
- **WHEN** the schema diff compares C oracle output with Rust replay output
- **THEN** it compares return value, call expression count, and call expression contexts
- **AND** a negative diff mutation of output or call expression metadata is detected

#### Scenario: Auto evidence preserves call expression context
- **WHEN** `auto_migrate --accept-existing-evidence` runs for `demo-call-expression`
- **THEN** the normalized translation plan records `bounded-call-expression`
- **AND** the context pack records `direct_call_edges`
- **AND** the final manifest binds accepted L3 evidence without claiming external callee semantic proof
