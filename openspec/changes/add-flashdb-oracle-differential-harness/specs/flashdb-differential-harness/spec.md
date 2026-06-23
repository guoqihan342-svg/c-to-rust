## ADDED Requirements

### Requirement: Rust fixture replay command
The `flashDB_rust` CLI SHALL provide a replay command that reads a deterministic fixture, executes it against the Rust implementation, and writes a machine-readable report.

`flashDB_rust` CLI 必须提供 replay 命令，用于执行确定性 fixture 并输出机器可读报告。

#### Scenario: Replay command writes report
- **WHEN** `flashdb-rust replay --fixture <path> --report <path>` is run
- **THEN** the Rust implementation executes the fixture and writes a replay report

### Requirement: Per-step replay results
The replay report SHALL include per-step operation id, operation name, status code, returned values or entries where applicable, image hash where requested, and stable error code for failed operations.

replay 报告必须包含逐步结果，便于根据错误栈定位第一处差异并自动打补丁。

#### Scenario: Failed step has stable error code
- **WHEN** a fixture step intentionally triggers an invalid key error
- **THEN** the report records a stable error code rather than relying only on human-readable error text

### Requirement: Differential comparison command
The `flashDB_rust` CLI SHALL provide a diff command that compares a Rust replay report with an oracle report and writes a comparison report.

`flashDB_rust` CLI 必须提供 diff 命令，用于比较 Rust replay report 与 oracle report。

#### Scenario: Matching reports pass
- **WHEN** Rust and oracle reports match for all non-accepted fields
- **THEN** the diff command exits successfully and writes a passing comparison report

### Requirement: Precise mismatch output
The diff command SHALL identify the first mismatching step, field path, expected value, actual value, and accepted-difference status.

diff 命令必须输出第一处不匹配的位置，而不是只返回泛化失败。

#### Scenario: Mismatch report points to first field
- **WHEN** an oracle report differs from the Rust report
- **THEN** the comparison report contains the first mismatching step id and field path

### Requirement: Existing commands remain compatible
The replay and diff additions SHALL NOT break existing `smoke`, `stress`, `inspect-image`, and `unsafe-scan` commands.

新增 replay/diff 不得破坏已有命令。

#### Scenario: Existing smoke command still runs
- **WHEN** the baseline verification script runs existing CLI commands
- **THEN** they continue to pass without changed arguments
