## ADDED Requirements

### Requirement: Comparable fixture
The system SHALL include a deterministic C/Rust comparable fixture that both Rust replay and C oracle can consume.

系统必须提供 C 与 Rust 共用的可比较 fixture。

#### Scenario: Fixture can be replayed by both runtimes
- **WHEN** Rust replay and C oracle run the comparable fixture
- **THEN** both reports contain matching step ids and operation names

### Requirement: C oracle fixture consumption
The C oracle producer SHALL pass the fixture path to the C executable and the executable SHALL consume the fixture operations instead of only running an unrelated hard-coded scenario.

C oracle 必须消费 fixture 输入，不能只输出另一套硬编码步骤。

#### Scenario: C report uses fixture step ids
- **WHEN** the C oracle producer runs with `--fixture fixtures/c-rust-smoke.json`
- **THEN** the C report contains the fixture operation ids

### Requirement: Replay-compatible C report
The C oracle report SHALL emit step objects with `id`, `op`, `status`, `code`, and comparable behavior fields.

C report 必须输出可被 Rust diff 识别的 step schema。

#### Scenario: C report has stable step codes
- **WHEN** a C fixture operation succeeds
- **THEN** its report step contains `status:"ok"` and `code:"OK"`

### Requirement: Schema-aware diff
The Rust diff command SHALL compare replay reports by schema fields instead of whole-file byte equality.

Rust diff 必须按 schema 比较，不能依赖整文件字符串完全一致。

#### Scenario: Metadata differs but behavior matches
- **WHEN** two reports differ only in metadata or accepted fields
- **THEN** diff passes

### Requirement: Behavior mismatch fails
The Rust diff command SHALL fail with the first mismatching step id and field path when non-accepted behavior differs.

非 accepted 行为字段不同必须失败。

#### Scenario: Value mismatch fails
- **WHEN** a C report returns a different KV value from the Rust report
- **THEN** diff exits non-zero and reports the mismatching step id and field path

### Requirement: CI runs C/Rust diff
CI SHALL run Rust replay for the comparable fixture, run the C oracle producer for the same fixture, and compare both reports.

CI 必须执行真正的 C/Rust 行为差分。

#### Scenario: C/Rust diff passes in CI
- **WHEN** GitHub Actions runs on Ubuntu
- **THEN** it fails unless the Rust-vs-C diff report passes for the comparable fixture
