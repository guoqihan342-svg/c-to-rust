## ADDED Requirements

### Requirement: SumI32Buffer Slice Has L3 Evidence
The system SHALL produce a complete L3 evidence package for the `sum_i32_buffer` demo slice.

系统必须为 `sum_i32_buffer(const int* values, int len, int* out)` demo slice 产出完整 L3 证据包，用来证明只读输入 buffer、长度 companion、bounded loop 和输出指针写入能够进入主验证链。

#### Scenario: Evidence manifest binds every required artifact
- **WHEN** the `sum_i32_buffer` L3 evidence package is validated
- **THEN** the evidence manifest includes context pack, slice spec, CFG, pointer graph, type map, C oracle, Rust replay report, schema diff, negative diff, unsafe scan, test translation, version/cache evidence, and summary evidence
- **AND** every referenced evidence file exists and is JSON-parseable unless it is an explicit log artifact

#### Scenario: C oracle and Rust replay are equivalent
- **WHEN** the demo slice is replayed for empty, single-item, multi-item, negative, and boundary-safe integer inputs
- **THEN** the Rust replay report matches the C oracle return code, status, and output sum for every case
- **AND** the schema diff reports zero mismatches

#### Scenario: Negative diff proves the comparator catches regressions
- **WHEN** the expected sum for at least one `sum_i32_buffer` case is intentionally mutated
- **THEN** the negative diff reports a mismatch
- **AND** the evidence records that the mismatch was expected and detected

### Requirement: SumI32Buffer Rust Boundary Is Safe
The generated or replayed Rust slice SHALL expose a safe public API for `sum_i32_buffer`.

Rust 侧必须用 safe 公共 API 表达输入 buffer 和输出值，不得把 C 的 `const int* values` 或 `int* out` 直接暴露为公共 raw pointer 参数。

#### Scenario: Public API does not expose raw pointers
- **WHEN** the Rust replay code for `sum_i32_buffer` is inspected by the unsafe scanner
- **THEN** the first-party unsafe count is zero
- **AND** the public function signature does not include `*const`, `*mut`, or `unsafe fn`

#### Scenario: Pointer input and output are represented as value evidence
- **WHEN** the Rust replay report is emitted
- **THEN** each case records the translated input values and output sum explicitly
- **AND** the report records that the source C reads were `values[i]` under `i < len` and the source C write was `out[0]`

### Requirement: SumI32Buffer Regression Gate Is Cheap And Deterministic
The regression gate SHALL validate the `sum_i32_buffer` evidence without requiring long-running fuzz or external network access.

回归门禁必须能在本地 deterministic smoke 中验证该 demo slice，不依赖网络，也不新增长耗时任务。

#### Scenario: One-round smoke validates sum_i32_buffer
- **WHEN** the full-regression script runs one smoke round with long stress skipped
- **THEN** it validates the `sum_i32_buffer` L3 evidence package
- **AND** it fails if required evidence is missing, stale, or semantically mismatched
