## ADDED Requirements

### Requirement: Deterministic operation fixtures
The system SHALL define deterministic fixture files that describe ordered KVDB, TSDB, persistence, and abnormal-data operations shared by the Rust replay consumer and the C oracle producer.

系统必须定义确定性的操作 fixture，让 Rust replay consumer 和 C oracle producer 使用同一份输入序列。

#### Scenario: Fixture lists ordered operations
- **WHEN** a fixture is loaded by the replay command
- **THEN** operations are executed in fixture order with stable ids and names

### Requirement: Fixture identity hash
The system SHALL compute and report a stable hash for every fixture used in replay or differential comparison.

系统必须为每个 fixture 计算稳定 hash，作为证据台账和 stale oracle 检测依据。

#### Scenario: Fixture hash appears in report
- **WHEN** replay or diff completes
- **THEN** the generated report contains the fixture path and fixture hash

### Requirement: KVDB fixture coverage
The fixture set SHALL cover KVDB set, get, delete, entries, compact, reopen, missing key, invalid key, oversized key, and capacity behavior.

fixture 集必须覆盖 KVDB 主干路径、异常路径和持久化 reopen 路径。

#### Scenario: KVDB main fixture replays
- **WHEN** the KVDB fixture is replayed
- **THEN** the report includes successful set/get/delete/entries/compact/reopen steps and expected abnormal failures

### Requirement: TSDB fixture coverage
The fixture set SHALL cover TSDB append, query, count by status, status update, reopen, empty range, and reversed range behavior.

fixture 集必须覆盖 TSDB append/query/count/status/reopen 的主干路径和范围边界。

#### Scenario: TSDB fixture replays
- **WHEN** the TSDB fixture is replayed
- **THEN** the report includes appended ids, query results, status counts, status updates, and reopened state

### Requirement: Accepted-difference schema
The fixture or comparison input SHALL allow accepted differences to be registered by stable id with reason, affected fields, and expiration or follow-up notes.

已知差异必须结构化记录，不能只写在聊天总结或自由文本里。

#### Scenario: Accepted difference is explicit
- **WHEN** a comparison ignores a known layout mismatch
- **THEN** the report identifies the accepted-difference id, reason, and affected fields
