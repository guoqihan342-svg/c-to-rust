## ADDED Requirements

### Requirement: TSDB Status Transition L3 Slice Selection
The system SHALL select `tsdb-status-transition` as a focused FlashDB L3 migration slice and SHALL record the public visible repeated-status boundary before implementation.

系统必须选择 `tsdb-status-transition` 作为聚焦的 FlashDB L3 迁移切片，并在实现前记录连续状态转换的公共可见边界。

#### Scenario: TSDB status transition slice is declared
- **WHEN** the TSDB status-transition L3 loop starts
- **THEN** it records `tsdb-status-transition` as the active slice with Rust APIs `TsDb::append`, `TsDb::set_status`, `TsDb::count_by_status`, `TsDb::query`, `TsDb::open`, replay operations `ts.append`, `ts.set_status`, `ts.count_status`, `ts.query`, `ts.reopen`, and C oracle operations `ts.append`, `ts.set_status`, `ts.count_status`, `ts.query`, `ts.reopen`

#### Scenario: TSDB status transition scope is public visible behavior only
- **WHEN** the slice contract is frozen
- **THEN** it states that latest-status query/count/reopen behavior is validated as public visible API semantics and does not claim clean, GC, physical deletion, sector rollover/full, capacity pressure, corrupt-image reopen, byte-for-byte layout, payload limits, or power-loss behavior

### Requirement: TSDB Status Transition Fixture Coverage
The system SHALL use a named L3 fixture that covers repeated TSDB status transitions on one entry and stable visibility after reopen.

系统必须使用命名 L3 fixture 覆盖同一条 TS entry 的连续状态转换，并验证 reopen 后可见性保持稳定。

#### Scenario: TSDB latest status wins after repeated updates
- **WHEN** `l3-tsdb-status-transition.json` is replayed
- **THEN** it appends two records, changes one entry through `user1`, `user2`, and `deleted`, counts final `deleted` as 1, counts final `written` as 1, and counts intermediate `user1` and `user2` as 0 after the final transition

#### Scenario: TSDB query reports final status only
- **WHEN** the fixture queries the covered time range after repeated status updates
- **THEN** the transitioned entry is reported with `status:"deleted"` and the untouched entry is reported with `status:"written"`

#### Scenario: TSDB latest status persists after reopen
- **WHEN** the fixture reopens the TSDB after repeated status updates
- **THEN** it recounts `deleted` as 1, recounts `written` as 1, and queries the same final visible statuses

### Requirement: TSDB Status Transition C Oracle And Rust Replay Diff
The system SHALL compare C and Rust TSDB status-transition behavior using the same fixture and schema-aware diff.

系统必须使用同一 fixture 和 schema-aware diff 对比 C/Rust TSDB 状态转换的可见行为。

#### Scenario: TSDB status transition reports use the same fixture
- **WHEN** L3 evidence is generated for `tsdb-status-transition`
- **THEN** `l3-tsdb-status-transition-c-oracle.json` and `l3-tsdb-status-transition-rust-report.json` reference the same fixture hash, fixture path, and source commit

#### Scenario: TSDB stale intermediate statuses cannot be accepted differences
- **WHEN** the schema-aware diff compares TSDB status-transition C and Rust reports
- **THEN** differences in `entry_id`, `timestamp`, query entry `status`, `value`, `ts_status`, `count`, step status, step code, operation success, operation id, operation name, or error semantics fail the L3 gate

#### Scenario: TSDB status transition negative regression is covered
- **WHEN** a report mutation changes the final query status or final count
- **THEN** the schema-aware diff rejects the mutation and records the first mismatch path

### Requirement: TSDB Status Transition Verification Evidence
The system SHALL persist TSDB status-transition L3 evidence under `validation/evidence/flashdb/` and SHALL rerun validation in escalating order.

系统必须在 `validation/evidence/flashdb/` 下持久化 TSDB 状态转换 L3 证据，并按由快到慢的顺序重新验证。

#### Scenario: TSDB status transition evidence files are written
- **WHEN** the slice reaches an evidence checkpoint
- **THEN** the agent writes machine-readable ContextPack, slice contract, impact set, Rust report, C oracle report, diff, negative diff, compile check, unsafe scan, unsafe ledger, cache metadata, performance smoke, and bilingual summary files

#### Scenario: TSDB status transition final verification is complete
- **WHEN** the TSDB status-transition slice is ready to close
- **THEN** `cargo fmt -- --check`, targeted Rust tests, `cargo test`, replay/diff, unsafe scan, `openspec validate run-flashdb-tsdb-status-transition-l3-loop --strict`, `openspec validate --all`, and `git diff --check` have durable evidence
