# pointer-arithmetic-output-write-l3-demo-slice Specification

## Purpose
This spec defines the `copy_i32_ptr_arith` L3 demonstration slice for bounded pointer-arithmetic output writes. It verifies that `*(out + i) = expr` is accepted only when the pointer graph and loop bound prove safe mutable-slice output behavior, while C oracle, Rust replay, schema-aware diff, negative diff, and unsafe evidence remain authoritative.
## Requirements
### Requirement: Copy I32 Pointer Arithmetic Output Write Demo
The system SHALL provide a `copy_i32_ptr_arith` L3 demo slice that validates bounded pointer-arithmetic output writes against a C oracle and Rust replay.

系统必须提供 `copy_i32_ptr_arith` L3 demo slice，用 C oracle 和 Rust replay 验证受限 pointer-arithmetic output write 的语义等价性。

#### Scenario: C oracle records output buffer writes
- **WHEN** the C oracle runs `copy_i32_ptr_arith(const int* values, int len, int* out)` over fixture cases
- **THEN** the oracle report records `out_values` as the observable output
- **AND** it records source write evidence `*(out + i)` and canonical write evidence `out[i]`
- **AND** it records source read evidence `*(values + i)` and canonical read evidence `values[i]` when the fixture uses input reads

#### Scenario: Rust replay matches C out_values
- **WHEN** the Rust replay runs the same fixture cases through a safe Rust boundary
- **THEN** the schema-aware diff compares `out_values` for every case
- **AND** the diff passes only when Rust `out_values` are equal to the C oracle `out_values`
- **AND** the negative diff mutates `out_values` and is detected

#### Scenario: L3 evidence manifest includes output-write artifacts
- **WHEN** the `copy_i32_ptr_arith` L3 evidence package is emitted
- **THEN** the manifest references slice contract, context pack, config profile, type map, CFG, pointer graph, test translation, C oracle, Rust report, schema diff, negative diff, rust check, unsafe scan, unsafe ledger, performance smoke, final verification, summary, and version/cache binding
- **AND** the pointer graph records the `bounded-pointer-arithmetic-output-write` rule id
- **AND** unsafe scan reports first-party non-test unsafe count as zero for this demo path

#### Scenario: Full regression includes semantic gate
- **WHEN** the short full-regression smoke suite runs
- **THEN** it validates the `demo/copy-i32-ptr-arith` auto evidence with semantic pass required
- **AND** OpenSpec validation for this change and all specs remains strict-clean
