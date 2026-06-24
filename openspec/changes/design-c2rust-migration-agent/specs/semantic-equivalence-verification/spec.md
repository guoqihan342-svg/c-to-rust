## ADDED Requirements

### Requirement: Machine-verifiable equivalence
The migration system SHALL prove semantic equivalence with machine-verifiable evidence. LLM judgment MUST NOT be accepted as equivalence evidence.

语义等价必须依靠机器证据，不接受“模型认为等价”。
#### Scenario: Verifying a migrated KVDB path
- **WHEN** KVDB set/get/delete/iterate/reopen is migrated
- **THEN** the Agent compares Rust behavior against C FlashDB or C2Rust baseline using the same operation sequence
- **THEN** return codes, read values, error mappings, flash image bytes, and reopen state match or have documented accepted mappings

### Requirement: Rust test generation
The migration system SHALL generate Rust unit tests, integration tests, and differential tests covering the main FlashDB paths. Generated tests MUST include success, boundary, error, GC/reopen, corrupted image, and persistence scenarios.

测试必须使用 Rust 主流测试框架，并覆盖主干路径、边界路径和错误路径。
#### Scenario: Generating main-path tests
- **WHEN** a migration slice is completed
- **THEN** the Agent creates or updates Rust tests for the slice
- **THEN** `cargo test` and `cargo nextest run` include those tests in verification

### Requirement: Extended verification gates
The migration system SHALL support coverage, property testing, fuzzing, and performance smoke gates for migrated code. Coverage SHOULD use `cargo llvm-cov nextest`, property tests SHOULD use `proptest`, fuzzing SHOULD use `cargo-fuzz`, and performance smoke SHOULD use Criterion or equivalent Rust benchmarks.

除普通测试外，还必须规划覆盖率、性质测试、fuzz 和性能 smoke 门禁。
#### Scenario: Validating persistent storage formats
- **WHEN** header, blob, sector status, CRC, or alignment logic is migrated
- **THEN** the Agent validates golden layout fixtures and corrupted-image cases
- **THEN** failing examples are minimized and added to regression tests
