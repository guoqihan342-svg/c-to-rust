## ADDED Requirements

### Requirement: L3 test translation reference
The L3 validation template SHALL reference code-test translation evidence for future L3 slices.

中文：L3 验证模板必须为后续 L3 切片引用 code-test translation 证据。

#### Scenario: L3 manifest references test translation evidence
- **WHEN** a future L3 evidence manifest is prepared
- **THEN** it includes `evidence.test_translation`
- **AND** the referenced artifact records source fixtures or C tests, Rust test files, Rust test names, main-path coverage, error-path coverage, negative cases, evidence links, and cache invalidation keys

### Requirement: Test translation does not replace L3 diff
The L3 validation template SHALL keep code-test translation evidence separate from semantic diff proof.

中文：L3 验证模板必须把 code-test translation 证据与 semantic diff 证明分开。

#### Scenario: Test translation exists but diff is missing
- **WHEN** test translation evidence exists but C oracle, Rust replay, schema diff, or negative diff evidence is missing
- **THEN** the L3 claim remains incomplete
