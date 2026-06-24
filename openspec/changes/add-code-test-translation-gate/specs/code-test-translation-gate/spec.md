## ADDED Requirements

### Requirement: Code-test translation manifest template
The system SHALL provide a reusable code-test translation manifest template for bounded C-to-Rust migration slices.

中文：系统必须为有边界的 C-to-Rust 迁移切片提供可复用 code-test translation manifest 模板。

#### Scenario: Template files are present
- **WHEN** an agent prepares an L2 or L3 migration slice
- **THEN** it can read `validation/test-translation-template/README.md`
- **AND** it can read `validation/test-translation-template/checklist.md`
- **AND** it can read `validation/test-translation-template/test-translation.schema.json`
- **AND** it can read `validation/test-translation-template/test-translation.example.json`

### Requirement: Migrated slices bind code and tests
The system SHALL require migrated L2/L3 slices to bind C tests, fixtures, or oracle expectations to Rust tests before success claims.

中文：系统必须要求已迁移的 L2/L3 切片在声明成功前，把 C 测试、fixture 或 oracle expectation 绑定到 Rust tests。

#### Scenario: Slice test mapping is recorded
- **WHEN** a slice reaches an L2 or L3 success checkpoint
- **THEN** the test translation manifest records source fixtures or C tests, Rust test files, Rust test names, cargo test commands, main-path coverage, error-path coverage, negative cases, evidence links, and known gaps

#### Scenario: Generated oracle fixture is the source mapping
- **WHEN** a slice has no direct upstream C test name
- **THEN** a generated oracle fixture or oracle expectation may be recorded as the source mapping
- **AND** the manifest still records the Rust test files, Rust test names, cargo commands, coverage categories, evidence links, and known gaps

### Requirement: Negative tests are part of translation evidence
The system SHALL include negative or regression tests in code-test translation evidence when the slice has behavior-diff gates.

中文：当切片包含行为 diff 门禁时，code-test translation 证据必须包含负向或回归测试。

#### Scenario: Negative diff gate exists
- **WHEN** a slice requires schema diff or negative diff evidence
- **THEN** the test translation manifest links at least one Rust negative test or mutation case to the diff evidence
- **AND** positive replay tests alone are insufficient for the manifest to pass

### Requirement: Test translation evidence is not semantic proof
The system SHALL state that test translation evidence complements but does not replace C/Rust semantic-equivalence gates.

中文：系统必须说明 test translation 证据是 C/Rust 语义等价门禁的补充，而不是替代品。

#### Scenario: Tests are mapped but diff evidence is missing
- **WHEN** Rust tests and fixtures are mapped but C oracle, Rust replay, schema diff, or negative diff evidence is missing for an L3 slice
- **THEN** the L3 claim remains incomplete

### Requirement: Test mapping drift invalidates reusable evidence
The system SHALL treat test mapping drift as invalidating affected context, cache, diff, and summary evidence.

中文：当测试映射漂移时，系统必须把受影响的 context、cache、diff 和 summary 证据视为失效。

#### Scenario: Test inputs or mappings change
- **WHEN** source commit, fixture hash, C oracle source, Rust test file hash, test name, cargo command, coverage entry, negative case, or accepted-difference boundary changes
- **THEN** cached ContextPack, PatchPlan suggestions, C oracle reports, Rust replay reports, diff conclusions, unsafe ledger, performance smoke, and summary claims must be regenerated or explicitly invalidated
