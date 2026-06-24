## ADDED Requirements

### Requirement: TSDB User2 Status L3 Slice Selection
The system SHALL select `tsdb-user2-status` as a focused FlashDB L3 migration slice and SHALL record its public visible status boundary before implementation.

系统必须选择 `tsdb-user2-status` 作为聚焦的 FlashDB L3 迁移切片，并在实现前记录其公开可见状态边界。

#### Scenario: TSDB user2 slice is declared
- **WHEN** the TSDB user2-status L3 loop starts
- **THEN** it records `tsdb-user2-status` as the active slice with Rust APIs `TsDb::append`, `TsDb::set_status`, `TsDb::count_by_status`, `TsDb::open`, replay operations `ts.append`, `ts.set_status`, `ts.count_status`, `ts.reopen`, and C oracle operations `ts.append`, `ts.set_status`, `ts.count_status`, `ts.reopen`

#### Scenario: TSDB user2 scope is public visible behavior only
- **WHEN** the slice contract is frozen
- **THEN** it states that `user2` set/count/reopen behavior is validated as public visible API semantics and does not claim clean, GC, physical deletion, sector rollover/full, capacity pressure, corrupt-image reopen, byte-for-byte layout, payload limits, or power-loss behavior

### Requirement: TSDB User2 Status Fixture Coverage
The system SHALL use a named L3 fixture that covers TSDB `user2` status behavior before and after reopen.

系统必须使用命名 L3 fixture 覆盖 TSDB `user2` 状态在 reopen 前后的行为。

#### Scenario: TSDB user2 status is set and counted
- **WHEN** `l3-tsdb-user2-status.json` is replayed
- **THEN** it appends at least two records, sets one entry to `user2`, emits `ts_status:"user2"`, counts `user2` as 1, and counts remaining `written` entries as 1

#### Scenario: TSDB user2 status persists after reopen
- **WHEN** the fixture reopens the TSDB after setting one entry to `user2`
- **THEN** it recounts `user2` as 1 after reopen

#### Scenario: TSDB user2 negative regression is covered
- **WHEN** a report mutation changes `ts_status`, `count`, `entry_id`, step status, step code, operation id, operation name, or operation success
- **THEN** the schema-aware diff rejects the mutation and records the first mismatch path

### Requirement: TSDB User2 C Oracle And Rust Replay Diff
The system SHALL compare C and Rust TSDB user2-status behavior using the same fixture and schema-aware diff.

系统必须使用同一个 fixture 和 schema-aware diff 对比 C/Rust TSDB user2-status 可见行为。

#### Scenario: TSDB user2 reports use the same fixture
- **WHEN** L3 evidence is generated for `tsdb-user2-status`
- **THEN** `l3-tsdb-user2-status-c-oracle.json` and `l3-tsdb-user2-status-rust-report.json` reference the same fixture hash, fixture path, and source commit

#### Scenario: TSDB user2 behavior fields cannot be accepted differences
- **WHEN** the schema-aware diff compares TSDB user2 C and Rust reports
- **THEN** differences in `entry_id`, `timestamp`, `ts_status`, `count`, step status, step code, operation success, operation id, operation name, or error semantics fail the L3 gate

### Requirement: TSDB User2 Verification Evidence
The system SHALL persist TSDB user2-status L3 evidence under `validation/evidence/flashdb/` and SHALL rerun validation in escalating order.

系统必须在 `validation/evidence/flashdb/` 下持久化 TSDB user2-status L3 证据，并按由快到慢的顺序重新验证。

#### Scenario: TSDB user2 evidence files are written
- **WHEN** the slice reaches an evidence checkpoint
- **THEN** the agent writes machine-readable ContextPack, slice contract, impact set, Rust report, C oracle report, diff, negative diff, compile check, unsafe scan, unsafe ledger, cache metadata, performance smoke, and bilingual summary files

#### Scenario: TSDB user2 final verification is complete
- **WHEN** the TSDB user2-status slice is ready to close
- **THEN** `cargo fmt -- --check`, targeted Rust tests, `cargo test`, replay/diff, unsafe scan, `openspec validate run-flashdb-tsdb-user2-status-l3-loop --strict`, `openspec validate --all`, and `git diff --check` have durable evidence
