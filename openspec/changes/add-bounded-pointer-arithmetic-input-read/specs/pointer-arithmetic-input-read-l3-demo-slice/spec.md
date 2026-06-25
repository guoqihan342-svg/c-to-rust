## ADDED Requirements

### Requirement: Sum I32 Pointer Arithmetic L3 Demo Slice
The system SHALL provide a committed `sum_i32_ptr_arith` L3 demo slice that proves bounded pointer arithmetic input-read translation through the existing semantic evidence gates.

系统必须提供已提交的 `sum_i32_ptr_arith` L3 demo slice，并通过现有语义证据门禁证明受限 pointer arithmetic input read 可被自动翻译和验证。

#### Scenario: Demo slice records pointer arithmetic C boundary
- **WHEN** the `demo-sum-i32-ptr-arith` slice spec is loaded
- **THEN** it records the C boundary `int sum_i32_ptr_arith(const int* values, int len, int* out)`
- **AND** the C source includes `total = total + *(values + i);`
- **AND** the Rust public API uses a safe slice-like input boundary

#### Scenario: Demo slice generates oracle and replay evidence
- **WHEN** L3 evidence is generated for `demo/sum-i32-ptr-arith`
- **THEN** the evidence includes a generated C oracle fixture, Rust replay report, schema diff, negative diff, rust check, unsafe scan, unsafe ledger, performance smoke, version/config binding, and final verification
- **AND** semantic verification passes only when C and Rust outputs match for the committed fixture corpus

#### Scenario: Negative diff proves mismatch detection
- **WHEN** the `sum_i32_ptr_arith` negative diff mutates an expected observable output
- **THEN** the diff evidence records `mutation_detected=true`
- **AND** the final L3 manifest links that negative diff evidence

#### Scenario: Unsafe budget remains zero for demo slice
- **WHEN** unsafe usage is scanned for the `sum_i32_ptr_arith` first-party Rust implementation
- **THEN** the evidence records zero first-party non-test unsafe usage for the slice
- **AND** the unsafe ratio remains below the project limit of 10%

#### Scenario: Full regression includes semantic smoke gate
- **WHEN** `scripts/run-full-regression.ps1` runs the short semantic gates
- **THEN** it validates the `demo/sum-i32-ptr-arith` auto-translation evidence with `--require-semantic-pass`
