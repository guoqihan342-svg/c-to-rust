## ADDED Requirements

### Requirement: StoreAddOne Slice Has L3 Evidence
The system SHALL produce a complete L3 evidence package for the `store_add_one` demo slice.

系统必须为 `store_add_one(int value, int* out)` demo slice 产出完整 L3 证据包，用来证明受限 `out[0]` 指针输出翻译能力进入主验证链。

#### Scenario: Evidence manifest binds every required artifact
- **WHEN** the `store_add_one` L3 evidence package is validated
- **THEN** the evidence manifest includes context pack, slice spec, CFG, pointer graph, type map, C oracle, Rust replay report, schema diff, negative diff, unsafe scan, and summary evidence
- **AND** every referenced evidence file exists and is JSON-parseable unless it is an explicit log artifact

#### Scenario: C oracle and Rust replay are equivalent
- **WHEN** the demo slice is replayed for boundary, nominal, and negative integer inputs
- **THEN** the Rust replay report matches the C oracle return code and output value for every case
- **AND** the schema diff reports zero mismatches

#### Scenario: Negative diff proves the comparator catches regressions
- **WHEN** the expected output for at least one `store_add_one` case is intentionally mutated
- **THEN** the negative diff reports a mismatch
- **AND** the evidence records that the mismatch was expected and detected

### Requirement: StoreAddOne Rust Boundary Is Safe
The generated or replayed Rust slice SHALL expose a safe public API for `store_add_one`.

Rust 侧必须使用 safe 公共 API 表达输出值，不得把 C 的 `int* out` 直接泄漏为公共 raw pointer 参数。

#### Scenario: Public API does not expose raw pointer
- **WHEN** the Rust replay code for `store_add_one` is inspected by the unsafe scanner
- **THEN** the first-party unsafe count is zero
- **AND** the public function signature does not include `*mut` or `unsafe fn`

#### Scenario: Pointer output is represented as value evidence
- **WHEN** the Rust replay report is emitted
- **THEN** each case records the translated output value explicitly
- **AND** the report records that the source C write was `out[0]`

### Requirement: StoreAddOne Regression Gate Is Cheap And Deterministic
The regression gate SHALL validate the `store_add_one` evidence without requiring long-running fuzz or external network access.

回归门禁必须能在本地 deterministic smoke 中验证该 demo slice，不依赖网络、不新增长耗时任务。

#### Scenario: One-round smoke validates store_add_one
- **WHEN** the full-regression script runs one smoke round with long stress skipped
- **THEN** it validates the `store_add_one` L3 evidence package
- **AND** it fails if required evidence is missing, stale, or semantically mismatched
