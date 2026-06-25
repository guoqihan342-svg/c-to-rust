## ADDED Requirements

### Requirement: External Callee Context Binding
The bounded auto-translation pipeline SHALL preserve declared external direct callee context when accepted L3 evidence is bound to an auto-generated candidate.

自动翻译管线在把 accepted L3 evidence 绑定到 auto-generated candidate 时，必须保留声明式 external direct callee context。

#### Scenario: Declared external callee evidence is bound
- **WHEN** a slice spec declares an external helper callee used by bounded direct call expressions
- **THEN** the normalized translation plan records the helper callee and call expression contexts
- **AND** the context pack records direct call edges, callee source boundary, stub kind, and semantic verification boundary
- **AND** missing declared callee context causes the slice-specific evidence test to fail

#### Scenario: Missing or unsupported external callee blocks false success
- **WHEN** a generated Rust draft contains a direct helper call whose callee is undeclared or has an unsupported signature
- **THEN** the pipeline MUST NOT mark rust-check or semantic pass as accepted by injecting an untracked helper
- **AND** blocked repairs or auto-translation events record the missing or unsupported callee reason
