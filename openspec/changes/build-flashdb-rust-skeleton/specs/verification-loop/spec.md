## ADDED Requirements

### Requirement: Baseline verification commands
The system SHALL provide documented commands for formatting, compiling, unit testing, integration testing, CLI smoke testing, stress-loop testing, unsafe scanning, OpenSpec validation, and diff whitespace validation.

系统必须提供可重复执行的基础验证命令，而不是只靠口头说明。

#### Scenario: Developer runs baseline verification
- **WHEN** the documented baseline verification commands are run
- **THEN** they complete successfully or report a precise missing optional tool or failing gate

### Requirement: Deterministic stress runner
The `flashDB_rust` CLI or scripts SHALL support deterministic loop testing with configurable loop count, seed, backend, scenario set, and report path.

CLI 或脚本必须支持可配置循环次数、随机种子、后端、场景集和报告路径，为 10000 轮验证做准备。

#### Scenario: 10000-loop command is available
- **WHEN** an operator requests a long verification run
- **THEN** the project exposes a command that can run 10000 deterministic iterations without changing source code

### Requirement: Production-like scenarios
The verification loop SHALL include production-like KVDB and TSDB operation sequences including repeated set/get/delete, blob writes, iteration, compaction, append/query/count/status, and reopen.

验证循环必须覆盖生产风格主路径，而不只是单条 happy path。

#### Scenario: Production-like loop succeeds
- **WHEN** the stress runner executes production-like scenarios on memory and file backends
- **THEN** all invariants hold and the report includes operation counts and duration

### Requirement: Abnormal data scenarios
The verification loop SHALL include abnormal and corrupted data scenarios such as empty keys, oversized keys, capacity exhaustion, invalid ranges, CRC mismatch, truncated records, and corrupted images.

验证循环必须覆盖异常数据和损坏数据。

#### Scenario: Corruption is detected
- **WHEN** the runner feeds a corrupted encoded record or image to the Rust implementation
- **THEN** the implementation returns a structured error and records the failure as an expected abnormal-path result

### Requirement: Reliability scenarios
The verification loop SHALL include persistence and reliability scenarios covering flush, reopen, repeated compaction, file-backed replay, and deterministic image hash reporting.

验证循环必须覆盖 flush、reopen、重复 compaction、文件后端 replay 和 image hash。

#### Scenario: Reopen loop preserves committed data
- **WHEN** a file-backed stress scenario repeatedly writes, flushes, reopens, and reads data
- **THEN** committed data remains readable and deleted data remains deleted

### Requirement: Performance smoke metrics
The verification loop SHALL record scenario duration, operation counts, read/write/erase counters, and bytes processed.

性能 smoke 必须输出机器可读指标，便于未来比较。

#### Scenario: Performance report is written
- **WHEN** a stress run completes
- **THEN** the report contains duration, operation count, backend counters, and bytes processed

### Requirement: Branch-oriented scenario coverage
The verification loop SHALL cover meaningful branches for success, missing keys, duplicate writes, deletes, empty ranges, reversed ranges, capacity limits, CRC failures, and backend errors where practical.

验证循环必须覆盖有意义的分支，而不是只跑随机成功路径。

#### Scenario: Branch summary is emitted
- **WHEN** the stress runner completes
- **THEN** it reports which scenario groups ran and how many iterations each group completed

### Requirement: Long-run evidence boundary
The system MUST NOT claim that 10000 full verification loops passed unless the actual 10000-loop command has been run to completion and its report is recorded.

除非真实运行 10000 轮并记录报告，否则不得声称 10000 轮已通过。

#### Scenario: Only smoke loops were run
- **WHEN** only a small smoke loop is executed
- **THEN** the result is reported as smoke evidence and not as completion of the 10000-loop requirement
