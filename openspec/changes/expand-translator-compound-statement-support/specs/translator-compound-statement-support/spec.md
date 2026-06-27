## ADDED Requirements

### Requirement: Compound Assignment Statements Are Translated
The bounded translator SHALL translate standalone C compound assignment statements in the supported structured subset.

#### Scenario: Compound assignment lowers to Rust
- **WHEN** a supported C function contains a standalone statement such as `value += 1;`
- **THEN** the translator emits the corresponding Rust compound assignment statement
- **AND** the generated plan records a compound-assignment translation rule
- **AND** the CFG evidence records the statement kind as compound assignment

#### Scenario: Clang-proven narrow integer promotion lowers through explicit casts
- **WHEN** typed IR clang lowering sees a standalone simple scalar compound assignment whose target/result types match and whose compute lhs/result types match, such as `uint8_t value; value += 1;`
- **THEN** the typed IR candidate lowers the operation through the compute type and casts back to the target type
- **AND** the generated Rust remains candidate generation only until semantic gates accept it

#### Scenario: Unknown expression still blocks translation
- **WHEN** a C function contains an expression statement outside the supported subset
- **THEN** the translator does not emit a Rust draft
- **AND** the translator records an unsupported syntax error

### Requirement: Increment And Decrement Statements Are Translated
The bounded translator SHALL translate standalone C pre/post increment and decrement statements in the supported structured subset.

#### Scenario: Increment statement lowers to Rust addition assignment
- **WHEN** a supported C function contains `i++` or `++i` as a standalone statement
- **THEN** the translator emits `i += 1;`
- **AND** the generated plan records an increment-decrement translation rule

#### Scenario: Decrement statement lowers to Rust subtraction assignment
- **WHEN** a supported C function contains `i--` or `--i` as a standalone statement
- **THEN** the translator emits `i -= 1;`
- **AND** the generated plan records an increment-decrement translation rule

#### Scenario: Expression-value increment is not accepted
- **WHEN** a C function uses increment or decrement in an expression value context
- **THEN** this change does not require the translator to accept that expression
