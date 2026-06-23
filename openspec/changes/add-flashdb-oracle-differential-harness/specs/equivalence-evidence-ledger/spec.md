## ADDED Requirements

### Requirement: Durable evidence ledger
The system SHALL write durable evidence files that summarize each replay or diff run, including command, fixture hash, report hashes, toolchain status, comparison status, and timestamp.

系统必须写入持久证据文件，避免只在聊天中说明验证结果。

#### Scenario: Evidence file is written
- **WHEN** replay or diff runs with an evidence path
- **THEN** a durable evidence file records the run identity and status

### Requirement: Report hash recording
The evidence ledger SHALL record stable hashes for Rust replay reports and C oracle reports when those reports exist.

证据台账必须记录 report hash，用于追踪 stale evidence 和复现问题。

#### Scenario: Report hashes are present
- **WHEN** both Rust and oracle reports are available
- **THEN** the ledger includes both report hashes

### Requirement: Toolchain status recording
The evidence ledger SHALL record whether C toolchain execution was run, skipped, or failed.

证据台账必须明确 C 工具链状态。

#### Scenario: Toolchain skip is visible
- **WHEN** C oracle generation is skipped locally
- **THEN** the ledger contains `SKIPPED_LOCAL_NO_C_TOOLCHAIN`

### Requirement: Unsafe budget preservation
The change SHALL preserve the first-party non-test Rust unsafe budget below 10% and SHOULD keep it at 0% for this harness.

本 change 必须保持 unsafe 比例低于 10%，并尽量继续保持 0%。

#### Scenario: Unsafe scan remains clean
- **WHEN** the unsafe scan command is run after replay/diff implementation
- **THEN** it reports no first-party non-test unsafe usage

### Requirement: Verification boundary clarity
The evidence ledger SHALL distinguish local Rust replay validation, Rust-to-checked-in-oracle comparison, CI C oracle generation, and full C/Rust semantic equivalence.

证据台账必须清楚区分本地 Rust replay 通过、对已存在 oracle 的比较通过、CI 生成 C oracle 通过，以及完整语义等价通过。

#### Scenario: Partial validation is labeled
- **WHEN** only local Rust replay and Rust report comparison have passed
- **THEN** the ledger labels the result as partial validation rather than full C/Rust equivalence
