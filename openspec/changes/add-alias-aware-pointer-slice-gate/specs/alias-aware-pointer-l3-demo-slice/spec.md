## ADDED Requirements

### Requirement: Add I32 Pair Pointer Arithmetic Alias Demo Slice
The system SHALL provide an `add_i32_pair_ptr_arith` L3 demo slice that exercises input/input alias tolerance and input/output alias preconditions without claiming complete alias safety.

系统必须提供 `add_i32_pair_ptr_arith` L3 demo slice，用来验证 input/input alias 容忍和 input/output alias 前置条件，同时不得声明完整 alias safety。

#### Scenario: Demo oracle records noalias and overlap-risk cases
- **WHEN** the C oracle runs `add_i32_pair_ptr_arith(const int* lhs, const int* rhs, int len, int* out)` over fixture cases
- **THEN** it records normal disjoint cases, a read/read alias case where `lhs` and `rhs` share values, and at least one rejected input/output overlap-risk case
- **AND** observable outputs include return code, input values, output values, source reads, source writes, canonical reads, canonical writes, and alias case metadata

#### Scenario: Rust replay binds safe noalias boundary
- **WHEN** the Rust replay uses a safe public API for the demo slice
- **THEN** the replay report records whether each case satisfies the safe precondition that `out` does not overlap `lhs` or `rhs`
- **AND** the schema diff compares observable outputs for accepted noalias cases
- **AND** cases outside the safe boundary are recorded as claim-boundary evidence rather than silently ignored

#### Scenario: Negative diff covers alias-sensitive output
- **WHEN** the negative diff mutates output values or alias case metadata
- **THEN** the diff gate detects the mutation
- **AND** the demo cannot pass if alias-sensitive fields are absent from the comparison

#### Scenario: Demo enters short full regression
- **WHEN** the short full-regression smoke suite runs
- **THEN** it validates the alias demo auto evidence with semantic pass and alias gate evidence required
- **AND** unsafe scan reports first-party non-test unsafe below 10%
